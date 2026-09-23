"""Pure, strict question/answer grammar. Limits are explicit input resource budgets."""
from copy import deepcopy
import hashlib
import json
import re

MAX_QUESTIONS = 30
MAX_CHOICES = 20
MAX_ANSWER_TEXT = 2000
KEY = re.compile(r'^[a-z][a-z0-9_]{0,39}$')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _text(value, limit, label, minimum=1):
    if not isinstance(value, str) or value != value.strip() or not minimum <= len(value) <= limit:
        raise ValueError(label + '须为已去首尾空格的有效文字')
    return value


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(label + '须在允许范围内填写整数，不能用真假值或小数替代')
    return value


def questions(value):
    if type(value) is not list or not 1 <= len(value) <= MAX_QUESTIONS:
        raise ValueError(f'问卷须有1至{MAX_QUESTIONS}题；上限为录入和展示预算')
    result = []; seen = set()
    allowed = {'key','label','kind','required','min_value','max_value','max_length','choices'}
    for raw in value:
        if type(raw) is not dict or not set(raw) <= allowed or not {'key','label','kind','required'} <= set(raw):
            raise ValueError('题目字段不完整或含有未知字段')
        key = raw['key']
        if not isinstance(key, str) or not KEY.fullmatch(key) or key in seen:
            raise ValueError('题目编号须为唯一的小写字母开头英文编号')
        seen.add(key)
        label = _text(raw['label'],180,'题目'); kind = raw['kind']
        if kind not in {'integer','boolean','text','choice'} or type(raw['required']) is not bool:
            raise ValueError('请明确题目类型和是否必答')
        low = raw.get('min_value'); high = raw.get('max_value')
        length = raw.get('max_length'); options = raw.get('choices', [])
        if kind == 'integer':
            _integer(low,-1000000,1000000,'最小值'); _integer(high,low,1000000,'最大值')
        elif low is not None or high is not None:
            raise ValueError('只有整数题可以设置数值范围')
        if kind == 'text': _integer(length,1,MAX_ANSWER_TEXT,'文字长度上限')
        elif length is not None: raise ValueError('只有文字题可以设置长度上限')
        if kind == 'choice':
            if type(options) is not list or not 2 <= len(options) <= MAX_CHOICES:
                raise ValueError('单选题须有2至20个选项；上限为展示预算')
            codes=set(); normalized=[]
            for option in options:
                if type(option) is not dict or set(option) != {'key','label'}:
                    raise ValueError('选项须包含编号和显示名称')
                code=_text(option['key'],40,'选项编号')
                if not KEY.fullmatch(code) or code in codes: raise ValueError('选项编号无效或重复')
                codes.add(code); normalized.append({'key':code,'label':_text(option['label'],80,'选项名称')})
            options=normalized
        elif options != []: raise ValueError('非单选题不能设置选项')
        # Legacy keys keep their established meaning; custom questions use new keys.
        if key=='satisfaction' and (kind!='integer' or low!=1 or high!=5):
            raise ValueError('原满意度编号只用于1至5分整数题；其他指标请另设编号')
        if key=='recommend' and kind!='boolean':raise ValueError('原是否推荐编号只用于是非题')
        result.append({'key':key,'label':label,'kind':kind,'required':raw['required'],
            'min_value':low,'max_value':high,'max_length':length,'choices':options})
    if not any(q['required'] for q in result):raise ValueError('至少明确一道必答题，不能发布可空白完成的问卷')
    return result


LEGACY_QUESTIONS = questions([
    {'key':'satisfaction','label':'本次服务满意度','kind':'integer','required':True,'min_value':1,'max_value':5},
    {'key':'recommend','label':'是否愿意推荐','kind':'boolean','required':True},
])
LEGACY_NAME = '客户服务问卷'


def answers(schema, value, *, completed):
    normalized=questions(schema)
    if type(value) is not dict:raise ValueError('问卷答案须按原题编号填写')
    keys={q['key'] for q in normalized}
    if not set(value) <= keys:raise ValueError('答案含有本次发放版本以外的题目')
    result={}
    for question in normalized:
        key=question['key']
        if key not in value:
            if completed and question['required']:raise ValueError('已完成问卷仍缺少必答题：'+question['label'])
            continue
        answer=value[key];kind=question['kind']
        if kind=='integer':_integer(answer,question['min_value'],question['max_value'],question['label'])
        elif kind=='boolean':
            if type(answer) is not bool:raise ValueError('是非题必须明确选择是或否，空值和文字不能替代')
        elif kind=='text':_text(answer,question['max_length'],question['label'])
        elif kind=='choice' and (not isinstance(answer,str) or answer not in {x['key'] for x in question['choices']}):
            raise ValueError('请选择本题原版本中的有效选项')
        result[key]=deepcopy(answer)
    return result
