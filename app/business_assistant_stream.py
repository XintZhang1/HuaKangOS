"""Bounded upstream SSE transport and downstream events; never emit raw reasoning."""
import asyncio
import json
import httpx
from fastapi import HTTPException
from starlette.responses import StreamingResponse
from .assistant_runtime_provider import SafeDeltas, provider_error


async def model_reply_stream(config,messages,thinking,emit):
    """Legacy SSE entry point; parsing and protection live in one adapter."""
    from .assistant_runtime_provider import model_reply_stream as shared_stream
    return await shared_stream(config,messages,thinking,emit)


async def streaming_response(db,request,user,session_id,request_id,content,thinking):
    from . import business_assistant_service as service
    queue=asyncio.Queue(maxsize=128)
    async def emit(event,data):await queue.put((event,data,None))
    async def run():
        try:
            result=await service.conversation(db,request,user,session_id,request_id,content,thinking=thinking,emit=emit)
            await emit('done',{'session':result})
        except HTTPException as exc:
            await queue.put(('error',{'message':service.safe_text(exc.detail,1000)},exc.status_code))
        except asyncio.CancelledError:raise
        except Exception:
            await queue.put(('error',{'message':'回复中断，请刷新对话核对结果'},500))
        finally:
            if not asyncio.current_task().cancelling():await queue.put(None)
    task=asyncio.create_task(run())
    async def stop():
        if not task.done():task.cancel()
        try:await asyncio.shield(task)
        except (asyncio.CancelledError,Exception):pass
    try:first=await queue.get()
    except BaseException:
        await stop();raise
    if first and first[0]=='error' and first[2]:
        await stop();raise HTTPException(first[2],first[1]['message'])
    async def events():
        item=first
        try:
            while item is not None:
                event,data,_=item
                yield 'event: '+event+'\ndata: '+json.dumps(data,ensure_ascii=False)+'\n\n'
                item=await queue.get()
        finally:await stop()
    class ManagedStream(StreamingResponse):
        async def __call__(self,scope,receive,send):
            # ASGI 2.4 signals disconnect through send(OSError), which need not
            # close a suspended body iterator immediately. Own task cleanup here.
            try:await super().__call__(scope,receive,send)
            finally:await stop()
    return ManagedStream(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


_RUNTIME_WAIT_SECONDS = 600
_RUNTIME_TERMINAL = frozenset({'succeeded', 'failed', 'cancelled'})


def _runtime_error(code, run_id, message, *, status=None):
    detail = {'message': message, 'run_id': run_id}
    if status is not None:
        detail['status'] = status
    return HTTPException(code, detail)


def _runtime_guard(auth):
    """Subscriptions never retain the request's get_db Session."""
    from sqlalchemy.orm import Session
    from .assistant_runtime_api import _guard
    with Session(bind=auth.bind, autoflush=False, expire_on_commit=False) as db:
        _guard(db, auth)


def _runtime_result(auth, run_id, body):
    """Read this exact terminal Run/reply before returning the old SessionView.

    A newer conversation reply, progress frame, or a model's completion claim
    cannot stand in for this Run's durable original response. This is read-only
    and independently rechecks the original HTTP identity before disclosure.
    """
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session
    from . import business_assistant_service as service
    from .assistant_runtime_api import _guard, _reading, _owned, _text
    from .assistant_runtime_models import Run
    from .assistant_runtime_queue import _digest
    from .business_assistant_models import AssistantMessage
    with Session(bind=auth.bind, autoflush=False, expire_on_commit=False) as db:
        try:
            with _reading(db, auth) as reader:
                run = _owned(reader, auth, Run, run_id)
                if (run.trigger_kind != 'user' or run.auth_kind != 'login'
                        or run.request_id != body.request_id
                        or run.trigger_key != f'user:{auth.session_id}:{body.request_id}'
                        or run.request_digest != _digest({'schema_version': 1, **body.model_dump(mode='json')})):
                    raise _runtime_error(409, run_id, '本次执行与原发送内容不一致，请刷新核对')
                original = reader.scalar(select(AssistantMessage).where(
                    AssistantMessage.session_id == auth.session_id,
                    AssistantMessage.request_id == body.request_id))
                if (original is None or original.store_id != auth.store_id or original.role != 'user'
                        or original.content != body.content or original.thinking is not body.thinking):
                    raise _runtime_error(409, run_id, '原消息记录不完整，请刷新核对本次执行')
                if run.status not in _RUNTIME_TERMINAL:
                    raise _runtime_error(503, run_id, '本次执行尚未结束，请按原执行编号继续查看')
                reply = reader.scalar(select(AssistantMessage).where(
                    AssistantMessage.session_id == auth.session_id,
                    AssistantMessage.request_id == body.request_id + ':reply'))
                if reply is not None and (reply.store_id != auth.store_id or reply.role != 'assistant'
                                           or reply.thinking is not body.thinking):
                    raise _runtime_error(409, run_id, '本次执行的回复记录不一致，请刷新核对')
                if run.status == 'succeeded' and reply is None:
                    raise _runtime_error(503, run_id, '本次执行缺少已保存的最终回复，请刷新核对')
                state, code = run.status, run.error_code
                text = _text(reply.content) if reply is not None else None
                session = service.session_view(reader, auth, auth.session_id)
            _guard(db, auth)
            return state, code, text, session
        except SQLAlchemyError:
            _guard(db, auth)
            raise _runtime_error(503, run_id, '暂时无法读取已保存的执行结果，请按原执行编号重查') from None


def _runtime_failure(run_id, status, code):
    if status == 'cancelled':
        return _runtime_error(409, run_id, '本次执行已停止，请核对已有卡片；原业务没有被撤销', status=status)
    return _runtime_error(503 if code == 'runtime_unavailable' else 409, run_id,
                          '本次执行未完成，请核对已保存的内容和卡片，不要重复办理', status=status)


async def _close_subscription(subscription):
    if subscription is not None:
        await subscription.aclose()


async def runtime_message(db, request, user, session_id, request_id, content, thinking):
    """Bounded legacy wait for the same persisted Run; never execute its work."""
    from .assistant_runtime_api import _capture, accept_run, open_event_stream
    from .assistant_runtime_schemas import RunCreate
    auth = _capture(db, request, user, session_id)
    body = RunCreate(request_id=request_id, content=content, thinking=thinking)
    run = await accept_run(db, request, auth, session_id, body)
    subscription = None
    try:
        _runtime_guard(auth)
        async with asyncio.timeout(_RUNTIME_WAIT_SECONDS):
            subscription = await open_event_stream(db, request, auth, run.id, after_seq=0)
            async for _ in subscription:
                if await request.is_disconnected():
                    raise _runtime_error(499, run.id,
                        '连接已断开，执行记录仍保留；请按原执行编号重新查看')
        state, code, _, session = _runtime_result(auth, run.id, body)
        if state != 'succeeded':
            raise _runtime_failure(run.id, state, code)
        _runtime_guard(auth)
        return session
    except TimeoutError:
        _runtime_guard(auth)
        raise _runtime_error(504, run.id,
            '本次等待已结束，执行记录仍保留；请按原执行编号刷新查看，重发须使用原发送编号') from None
    except HTTPException as exc:
        if type(exc.detail) is dict and exc.detail.get('run_id') == run.id:
            raise
        # Keep a fixed explanation; no cached response or arbitrary native
        # exception body is exposed after a permission/subscription failure.
        raise _runtime_error(exc.status_code, run.id,
            '当前无法继续查看本次执行，请重新登录或刷新后按原执行编号核对') from None
    except Exception:
        raise _runtime_error(503, run.id,
            '暂时无法继续等待本次执行，请按原执行编号刷新核对已保存的结果') from None
    finally:
        await _close_subscription(subscription)


async def runtime_streaming_response(db, request, user, session_id, request_id, content, thinking):
    """Adapt durable events to the legacy delta-only client without repetition.

    Run progress is a revisable full snapshot. The old client cannot replace
    text, so it receives processing status and then this Run's saved final reply
    exactly once. Disconnect only closes these iterators, never the actual Run.
    """
    from .assistant_runtime_api import _capture, accept_run, open_event_stream
    from .assistant_runtime_schemas import RunCreate
    auth = _capture(db, request, user, session_id)
    body = RunCreate(request_id=request_id, content=content, thinking=thinking)
    run = await accept_run(db, request, auth, session_id, body)
    try:
        _runtime_guard(auth)
        # The awaitable performs initial permission/cursor checks before headers.
        subscription = await open_event_stream(db, request, auth, run.id, after_seq=0)
    except HTTPException as exc:
        raise _runtime_error(exc.status_code, run.id,
            '当前无法订阅本次执行，请重新登录或刷新后按原执行编号核对') from None
    except Exception:
        raise _runtime_error(503, run.id,
            '暂时无法订阅本次执行，请按原执行编号刷新核对已保存的结果') from None
    closed = False

    async def stop():
        nonlocal closed
        if not closed:
            await _close_subscription(subscription)
            closed = True

    def frame(kind, value):
        return 'event: ' + kind + '\ndata: ' + json.dumps(value, ensure_ascii=False) + '\n\n'

    async def events():
        try:
            _runtime_guard(auth)
            yield frame('status', {'phase': 'tool', 'round': 0, 'run_id': run.id})
            async with asyncio.timeout(_RUNTIME_WAIT_SECONDS):
                async for event in subscription:
                    if await request.is_disconnected():
                        return
                    if event is None:
                        _runtime_guard(auth)
                        yield ': heartbeat\n\n'
                    elif event.type in {'run.started', 'tool.finished', 'proposal.prepared', 'plan.updated'}:
                        _runtime_guard(auth)
                        yield frame('status', {'phase': 'tool', 'round': 0, 'run_id': run.id})
                    # run.progress is intentionally not converted into deltas.
                    # A terminal event is not the saved final AssistantMessage.
            state, code, text, session = _runtime_result(auth, run.id, body)
            if state != 'succeeded':
                error = _runtime_failure(run.id, state, code)
                _runtime_guard(auth)
                yield frame('error', error.detail)
            elif text:
                _runtime_guard(auth)
                yield frame('delta', {'text': text, 'run_id': run.id})
            _runtime_guard(auth)
            yield frame('done', {'session': session, 'run_id': run.id})
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            yield frame('error', {'message': '本次等待已结束，请按原执行编号刷新查看；执行不会因断流取消',
                                  'run_id': run.id, 'status_code': 504})
        except HTTPException as exc:
            # No done/session frame follows an expired identity or read error.
            message = (exc.detail.get('message') if type(exc.detail) is dict
                       and exc.detail.get('run_id') == run.id else
                       '当前无法继续查看本次执行，请重新登录或刷新后按原执行编号核对')
            yield frame('error', {'message': message, 'run_id': run.id, 'status_code': exc.status_code})
        except Exception:
            yield frame('error', {'message': '回复订阅中断，请按原执行编号刷新核对已保存的结果',
                                  'run_id': run.id, 'status_code': 503})
        finally:
            await stop()

    class ManagedRuntimeStream(StreamingResponse):
        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                # ASGI 2.4 may stop at send(OSError) with the generator suspended
                # at a yield. Close it explicitly, without a queue cancellation.
                await self.body_iterator.aclose()
                await stop()

    return ManagedRuntimeStream(events(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
