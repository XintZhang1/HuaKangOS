#!/usr/bin/env bash
# =============================================================================
# deploy/sg/install.sh
# 新加坡 Vultr「构建机」初始化脚本
#   （207.148.126.193 / 主机名 binance-bot / Ubuntu 22.04 / 1vCPU 2GB / 系统时区 Etc/UTC）
#
# 【硬性规则 —— 本脚本绝不违反】
#   * 不碰 ufw / iptables / nftables 规则，不开关任何端口。
#   * 不改全局代理设置：不写 /etc/environment、/etc/profile.d、apt.conf、docker 代理、
#     pip/npm/git 全局代理。这台机器上跑着与本项目无关的生产量化/加密交易服务。
#   * 不重启、不停用、不改动任何既有服务。本脚本只处理它自己安装的 docker，
#     且 docker 已在运行时保持原状（不 restart、不改 /etc/docker/daemon.json）。
#   * 不删除任何已有文件；已存在的 /etc/huakangos-builder.env 与 SSH 密钥绝不覆盖。
#
# 【本脚本做什么】
#   1. 用 Ubuntu apt 镜像安装 docker.io、git、python3-venv、ca-certificates
#      （DEBIAN_FRONTEND=noninteractive）。
#   2. 建构建机用户 hkbuild（家目录 /opt/huakangos-builder）并加入 docker 组。
#   3. 建 {repository,state,bin,src,.ssh} 与 venv；把 deploy/sg/hk_builder 以 root:root 0755
#      安装到 /opt/huakangos-builder/bin/hk_builder。
#   4. venv 只装构建机真正 import 的东西：pydantic、python-dotenv。
#      构建机不跑 Web 业务，不需要 fastapi/uvicorn/sqlalchemy/alembic/argon2 等。
#   5. 生成 /etc/huakangos-builder.env（仅当文件不存在），写入 BuilderConfig 读取的
#      全部 17 个 HKB_* 变量：安全默认值、HKB_TRUSTED_SHA 留空、密钥留空。
#   6. 从 https://api.github.com/meta 抓取 GitHub 公布的 SSH 主机密钥写入 hkbuild 的
#      known_hosts（git-over-ssh 不做首次连接信任 TOFU）。
#   7. 把 HKB_TRUSTED_SHA 指向的可信提交检出到 /opt/huakangos-builder/src，并**只构建一次**
#      隔离测试镜像（带 dealerdesk.trusted.sha=<SHA> 标签）。HKB_TRUSTED_SHA 为空或不是
#      40 位十六进制提交号时明确报错并以非零码退出。
#   8. 打印：如何加入阿里云控制器公钥、如何登记 GitHub deploy key、如何核对主机指纹。
#
# 【本脚本故意不做什么】
#   * 绝不从 AI 候选重建受信任测试镜像。maintenance/images.py 的 trusted_test_image()
#     会比对镜像标签与 HKB_TRUSTED_SHA，不一致就拒绝测试候选。本脚本只在标签不一致时
#     从固定提交重建。
#   * 不改 sshd 配置（不打开 PermitUserEnvironment 等）：授权只靠 authorized_keys 的
#     restrict,command= 强制命令，配置由 hk_builder 自己从 /etc/huakangos-builder.env 读取。
#   * 不安装 Web/业务依赖、不生成任何密钥（deploy key 由人工在下一步生成登记）。
#
# 幂等：可以反复执行。
# =============================================================================
set -euo pipefail

readonly BUILDER_USER='hkbuild'
readonly BUILDER_ROOT='/opt/huakangos-builder'
readonly BUILDER_ENV='/etc/huakangos-builder.env'
readonly REPO_DIR="${BUILDER_ROOT}/repository"
readonly STATE_DIR="${BUILDER_ROOT}/state"
readonly BIN_DIR="${BUILDER_ROOT}/bin"
readonly SSH_DIR="${BUILDER_ROOT}/.ssh"
readonly SRC_DIR="${BUILDER_ROOT}/src"
readonly VENV_DIR="${BUILDER_ROOT}/venv"
readonly WRAPPER_PATH="${BIN_DIR}/hk_builder"
readonly TRUSTED_LABEL_KEY='dealerdesk.trusted.sha'
readonly KNOWN_HOSTS="${SSH_DIR}/known_hosts"

info() { printf '\n\033[1;32m[hk-builder]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[警告]\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die '请用 root 运行：sudo bash deploy/sg/install.sh'
command -v apt-get >/dev/null 2>&1 || die '本脚本只支持 Debian/Ubuntu（找不到 apt-get）'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly WRAPPER_SRC="${SCRIPT_DIR}/hk_builder"

# -----------------------------------------------------------------------------
# 1. apt 依赖（只装这些；不动代理、不动防火墙、不动既有服务）
# -----------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
info '步骤 1/8：安装 docker.io / git / python3-venv / ca-certificates'
apt-get update || die 'apt-get update 失败：请检查本机 apt 源与网络（本脚本不会修改任何代理设置）'
apt-get install -y --no-install-recommends docker.io git python3-venv ca-certificates \
  || die 'apt 安装失败：请检查磁盘空间与镜像可达性后重试'

if systemctl is-active --quiet docker; then
  info 'docker 已在运行：保持原状（不 restart、不改 daemon 配置、不动其它容器）'
else
  systemctl enable --now docker >/dev/null 2>&1 || warn 'docker 启动失败，请手动检查 systemctl status docker'
fi
docker version --format '{{.Server.Version}}' >/dev/null 2>&1 \
  || die 'docker 守护进程不可用：构建机无法构建/测试候选。请检查 systemctl status docker 后重试'
info "docker 就绪：$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '未知版本')"

# -----------------------------------------------------------------------------
# 2. 构建机用户与目录
# -----------------------------------------------------------------------------
info '步骤 2/8：创建用户与目录'
if id -u "${BUILDER_USER}" >/dev/null 2>&1; then
  info "用户 ${BUILDER_USER} 已存在，跳过创建"
else
  # 必须是可登录 shell：sshd 会用 $SHELL -c '<forced command>' 执行强制命令。
  # 该账号没有密码（useradd 默认锁定），只能靠 authorized_keys 里那一把受限公钥进入。
  useradd --create-home --home-dir "${BUILDER_ROOT}" --shell /bin/bash \
    --comment 'HuaKangOS builder (forced command only)' "${BUILDER_USER}" \
    || die "创建用户 ${BUILDER_USER} 失败"
  info "已创建用户 ${BUILDER_USER}（家目录 ${BUILDER_ROOT}，无密码）"
fi

# docker 组等价于 root。构建机只执行固定动词白名单（status/context/candidate/image/
# publish/revert/prune），AI 候选代码只在容器里跑；但 hkbuild 本身仍等价于本机 root，
# 所以这台机器上不能放与构建无关的生产密钥，也不要把量化服务的凭据交给它。
usermod -aG docker "${BUILDER_USER}"
info "已把 ${BUILDER_USER} 加入 docker 组（root 等价，明确接受的取舍）"

install -d -m 0750 -o "${BUILDER_USER}" -g "${BUILDER_USER}" "${BUILDER_ROOT}"
install -d -m 0750 -o "${BUILDER_USER}" -g "${BUILDER_USER}" "${REPO_DIR}"
install -d -m 0700 -o "${BUILDER_USER}" -g "${BUILDER_USER}" "${STATE_DIR}"
install -d -m 0700 -o "${BUILDER_USER}" -g "${BUILDER_USER}" "${SSH_DIR}"
install -d -m 0750 -o "${BUILDER_USER}" -g "${BUILDER_USER}" "${SRC_DIR}"
install -d -m 0755 -o root -g root "${BIN_DIR}"

# -----------------------------------------------------------------------------
# 3. 安装强制命令包装器（root:root 0755，绝不能全局可写）
# -----------------------------------------------------------------------------
info '步骤 3/8：安装 hk_builder 强制命令包装器'
[[ -f "${WRAPPER_SRC}" ]] || die "找不到 ${WRAPPER_SRC}：请连同 deploy/sg/hk_builder 一起上传"
install -m 0755 -o root -g root "${WRAPPER_SRC}" "${WRAPPER_PATH}"
if [[ -n "$(find "${WRAPPER_PATH}" -perm -0002 -print -quit 2>/dev/null)" ]]; then
  die "${WRAPPER_PATH} 是全局可写的：能改它的人就能以 ${BUILDER_USER} 身份执行任意命令，已中止"
fi
info "已安装 ${WRAPPER_PATH}（root:root 0755）"

# -----------------------------------------------------------------------------
# 4. builder venv：只装构建机 import 的东西
#    构建机侧代码路径：maintenance/builder/* → maintenance/{config,gitops,images,
#    policy,sandbox,transport,window} → app/config.py。
#    第三方依赖只有 pydantic（policy.py）与 python-dotenv（app/config.py 的 load_dotenv）。
# -----------------------------------------------------------------------------
info '步骤 4/8：准备构建机 venv（只装 pydantic 与 python-dotenv）'
PYTHON_BIN="$(command -v python3 || true)"
[[ -n "${PYTHON_BIN}" ]] || die '找不到 python3：请先 apt-get install -y python3 python3-venv'
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  sudo -u "${BUILDER_USER}" -H "${PYTHON_BIN}" -m venv "${VENV_DIR}" \
    || die '创建构建机 venv 失败：请确认已安装 python3-venv'
fi
# 统一用 sudo -H：让 HOME 指向 hkbuild 家目录，pip/git 不会误读 root 的配置与缓存。
# 版本与 requirements.txt 保持一致，避免构建机上的 pydantic 与控制器校验行为不同。
sudo -u "${BUILDER_USER}" -H "${VENV_DIR}/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
sudo -u "${BUILDER_USER}" -H "${VENV_DIR}/bin/python" -m pip install --upgrade \
  'pydantic==2.13.4' 'python-dotenv==1.2.2' \
  || die '安装 pydantic / python-dotenv 失败：请检查网络后重试（本脚本不修改全局代理）'
sudo -u "${BUILDER_USER}" -H "${VENV_DIR}/bin/python" -c 'import pydantic, dotenv' \
  || die '构建机 venv 依赖自检失败'
info '构建机 venv 就绪（不含 Web 栈：构建机不跑业务服务）'

# -----------------------------------------------------------------------------
# 5. 环境文件：只在新装时生成，绝不覆盖；列出 BuilderConfig 读取的全部 HKB_* 变量
# -----------------------------------------------------------------------------
if [[ -e "${BUILDER_ENV}" ]]; then
  info "步骤 5/8：${BUILDER_ENV} 已存在，保持不变（本脚本永不覆盖内容）"
else
  cat >"${BUILDER_ENV}" <<'BUILDERENV'
# HuaKangOS / DealerDesk 构建机环境文件（由 deploy/sg/install.sh 生成，仅当文件不存在时）
# 读取方：/opt/huakangos-builder/bin/hk_builder → maintenance/config.py 的 BuilderConfig。
# 格式：KEY=VALUE，不加引号、值内不留空格、不用 export，可写 # 注释；文件必须保持 LF。
# 权限：hkbuild:hkbuild 0600（强制命令以 hkbuild 身份运行，必须由它可读）。
# 变量名必须与 maintenance/config.py 中的 BuilderConfig 完全一致，不要自行改名。

# --- 代码仓库（必填：无内嵌凭据的 HTTPS 或 git@host:path）---
HKB_REPO_URL=
# 审批卡片 compare 链接用的仓库页面（必填，https）
HKB_REPO_WEB_URL=
HKB_BASE_BRANCH=main

# --- 构建机根目录（repository/state/src/venv 都在其下；hk_builder 固定使用此路径）---
HKB_ROOT=/opt/huakangos-builder

# --- 镜像名 ---
HKB_TEST_IMAGE=dealerdesk-tests:0.2
HKB_APP_IMAGE_PREFIX=huakangos-app

# --- 用于 git push 的 deploy key（私钥只在本机，0600）---
HKB_GIT_SSH_KEY=/opt/huakangos-builder/.ssh/github_deploy_ed25519

# --- 超时与磁盘闸门（1vCPU/2GB，构建慢是正常的）---
HKB_TEST_TIMEOUT=1800
HKB_BUILD_TIMEOUT=3600
HKB_MIN_FREE_GB=3

# --- 维护窗口（显式时区，与构建机系统时区 Etc/UTC 无关）---
HKB_WINDOW_TZ=Asia/Shanghai
HKB_WINDOW_START=22:00
HKB_WINDOW_END=06:00
# 本机量化交易每 4 小时一次（00:01 / 04:01 Asia/Shanghai）：这两个区间必须让行
HKB_WINDOW_BANS=23:50-00:30,03:50-04:30
HKB_MIN_SEGMENT_MINUTES=20

# --- 让行的生产 systemd 单元（强烈建议填）---
# maintenance/window.py 的 quant_state() 用 `systemctl is-active <单元名>` 判断；
# 留空 = 不检查量化任务，只靠时间窗口。请先看清本机在跑什么：
#     systemctl list-units --type=service --state=running
# 然后把与本项目无关的生产量化/交易服务单元名（逗号分隔）填进来，例如：
#     HKB_QUANT_UNITS=quant-trader-a.service,quant-trader-b.service
HKB_QUANT_UNITS=

# --- 受信任基线提交（必填：40 位十六进制提交号）---
# 隔离测试镜像就是从这个提交构建一次并打上标签的；标签必须等于这个值，
# 否则 maintenance/images.py 的 trusted_test_image() 拒绝用该镜像测试候选。
HKB_TRUSTED_SHA=
BUILDERENV
  info "已生成 ${BUILDER_ENV}（HKB_TRUSTED_SHA 留空，待人工填写）"
fi
# 每次运行都重申权限（只改属主/权限，绝不改内容）：强制命令以 hkbuild 身份运行，
# 必须由 hkbuild 可读，且不应让同机其它账号读到仓库地址与窗口配置。
chown "${BUILDER_USER}:${BUILDER_USER}" "${BUILDER_ENV}"
chmod 0600 "${BUILDER_ENV}"

# -----------------------------------------------------------------------------
# 6. GitHub 主机密钥 → hkbuild 的 known_hosts（避免首次连接信任 TOFU）
# -----------------------------------------------------------------------------
info '步骤 6/8：写入 GitHub 公布的 SSH 主机密钥'
if [[ -s "${KNOWN_HOSTS}" ]] && grep -q '^github\.com ' "${KNOWN_HOSTS}"; then
  info 'known_hosts 已包含 github.com，跳过（保持已有内容不变）'
else
  if python3 - "${KNOWN_HOSTS}" <<'HOSTKEYS'
import json, sys, urllib.request
target = sys.argv[1]
with urllib.request.urlopen('https://api.github.com/meta', timeout=20) as response:
    meta = json.load(response)
keys = [str(key).strip() for key in (meta.get('ssh_keys') or []) if str(key).strip()]
if not keys:
    raise SystemExit('api.github.com/meta 未返回 ssh_keys')
with open(target, 'w', encoding='utf-8') as handle:
    for key in keys:
        handle.write('github.com ' + key + '\n')
print('已写入 %d 条 GitHub 主机密钥' % len(keys))
HOSTKEYS
  then
    chown "${BUILDER_USER}:${BUILDER_USER}" "${KNOWN_HOSTS}"
    chmod 0600 "${KNOWN_HOSTS}"
    info "已从 https://api.github.com/meta 写入 ${KNOWN_HOSTS}（0600）"
  else
    rm -f -- "${KNOWN_HOSTS}"
    die '抓取 GitHub 主机密钥失败：请检查本机到 api.github.com 的网络（本脚本不会修改任何代理设置），修好后重新运行本脚本。
这里刻意不使用 ssh-keyscan 的首次连接信任，以免把 git push 的目标主机交给未知密钥。'
  fi
fi

# -----------------------------------------------------------------------------
# 7. 可信检出 + 受信任测试镜像（从固定提交构建一次）
# -----------------------------------------------------------------------------
info '步骤 7/8：准备可信检出与受信任测试镜像'
# 先校验格式再 source：写成 KEY = VALUE、行首 export、值里带空格都会让 source 变成
# 执行命令（危险且难查），这里直接拒收并指出行号。
BAD_LINES="$(grep -nEv '^[A-Za-z_][A-Za-z0-9_]*=|^[[:space:]]*(#|$)' "${BUILDER_ENV}" || true)"
if [[ -n "${BAD_LINES}" ]]; then
  warn '以下行不符合 KEY=VALUE 格式（不要加引号 / export / 等号两侧空格）：'
  printf '%s\n' "${BAD_LINES}" >&2
  die "请修正 ${BUILDER_ENV} 后重新运行本脚本"
fi
# shellcheck disable=SC1090
set -a
. "${BUILDER_ENV}"
set +a

if [[ "${HKB_ROOT}" != "${BUILDER_ROOT}" ]]; then
  die "HKB_ROOT=${HKB_ROOT} 与 deploy/sg/hk_builder 固定使用的 ${BUILDER_ROOT} 不一致：
强制命令按固定路径寻找可信检出与 venv，请把 HKB_ROOT 改回 ${BUILDER_ROOT}。"
fi
[[ -n "${HKB_TEST_IMAGE:-}" ]] || die 'HKB_TEST_IMAGE 为空：请填写镜像标签（默认 dealerdesk-tests:0.2）后重新运行'

if [[ -z "${HKB_TRUSTED_SHA:-}" ]]; then
  warn 'HKB_TRUSTED_SHA 为空：拒绝构建受信任测试镜像。'
  cat >&2 <<'SHAFIX'
请在 /etc/huakangos-builder.env 中填写作为可信基线的 40 位提交号并重新运行本脚本：
    HKB_TRUSTED_SHA=<在人工审阅过的基线检出里执行 git log -1 --format=%H 的结果>
同时确认 HKB_REPO_URL / HKB_REPO_WEB_URL 已填写，并先生成、登记构建机的 deploy key：
    sudo -u hkbuild -H ssh-keygen -t ed25519 -a 100 -N '' \
      -C 'huakangos-builder@binance-bot' \
      -f /opt/huakangos-builder/.ssh/github_deploy_ed25519
    cat /opt/huakangos-builder/.ssh/github_deploy_ed25519.pub
（把公钥登记为该专用仓库的 Deploy Key，并勾选允许写入：publish 动词要快进主分支。）
本脚本不会静默继续，也不会用别的提交顶替。
SHAFIX
  exit 1
fi
if [[ ! "${HKB_TRUSTED_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  die "HKB_TRUSTED_SHA 不是 40 位小写十六进制提交号：'${HKB_TRUSTED_SHA}'。请修正后重新运行本脚本（拒绝用分支名或短号顶替）。"
fi

GIT_SSH_CMD="ssh -i ${HKB_GIT_SSH_KEY} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${KNOWN_HOSTS}"

if [[ ! -d "${SRC_DIR}/.git" ]]; then
  [[ -n "${HKB_REPO_URL:-}" ]] || die 'HKB_REPO_URL 为空：请在 /etc/huakangos-builder.env 中填写专用仓库地址后重新运行'
  [[ -n "${HKB_GIT_SSH_KEY:-}" && -f "${HKB_GIT_SSH_KEY}" ]] \
    || die "HKB_GIT_SSH_KEY=${HKB_GIT_SSH_KEY:-（空）} 指向的私钥不存在：请先生成构建机 deploy key（见上面的 ssh-keygen 提示）后重新运行"
  info "克隆可信检出到 ${SRC_DIR}（只克隆，不修改远端）"
  sudo -u "${BUILDER_USER}" -H env GIT_SSH_COMMAND="${GIT_SSH_CMD}" GIT_TERMINAL_PROMPT=0 \
    git clone --quiet "${HKB_REPO_URL}" "${SRC_DIR}" \
    || die '克隆失败：请核对 HKB_REPO_URL、deploy key 是否已登记、以及 known_hosts 是否包含 github.com'
else
  info "可信检出已存在于 ${SRC_DIR}，只做 fetch"
  sudo -u "${BUILDER_USER}" -H env GIT_SSH_COMMAND="${GIT_SSH_CMD}" GIT_TERMINAL_PROMPT=0 \
    git -C "${SRC_DIR}" fetch --quiet --prune --tags origin || die 'git fetch 失败：请核对网络与 deploy key'
fi
sudo -u "${BUILDER_USER}" -H env GIT_SSH_COMMAND="${GIT_SSH_CMD}" GIT_TERMINAL_PROMPT=0 \
  git -C "${SRC_DIR}" checkout --quiet --detach --force "${HKB_TRUSTED_SHA}" \
  || die "无法检出 HKB_TRUSTED_SHA=${HKB_TRUSTED_SHA}：该提交不在仓库中（或被 force-push 抹掉）"
ACTUAL_SHA="$(sudo -u "${BUILDER_USER}" -H git -C "${SRC_DIR}" rev-parse HEAD)"
[[ "${ACTUAL_SHA}" == "${HKB_TRUSTED_SHA}" ]] \
  || die "检出结果 ${ACTUAL_SHA} 与 HKB_TRUSTED_SHA 不一致，拒绝继续"

# 受信任测试镜像：只从这里构建一次。
# 绝不能用 AI 候选、或用 AI 改过的 Dockerfile 重建它 —— maintenance/images.py 会比对
# 镜像标签 dealerdesk.trusted.sha 与 HKB_TRUSTED_SHA，不一致就拒绝测试候选。
# 这一步会从 Docker Hub 拉取基础镜像 python:3.12-slim（构建机可以访问外网）；
# 之后候选镜像构建用 --pull=false，不依赖外网。
CURRENT_LABEL="$(docker image inspect "${HKB_TEST_IMAGE}" \
  --format "{{index .Config.Labels \"${TRUSTED_LABEL_KEY}\"}}" 2>/dev/null || true)"
if [[ "${CURRENT_LABEL}" == "${HKB_TRUSTED_SHA}" ]]; then
  info "受信任测试镜像 ${HKB_TEST_IMAGE} 已存在且标签一致（${HKB_TRUSTED_SHA}），跳过重建"
else
  info "构建受信任测试镜像 ${HKB_TEST_IMAGE}（基线 ${HKB_TRUSTED_SHA}）"
  ( cd "${SRC_DIR}" && docker build -f maintenance/Dockerfile.test \
      --label "${TRUSTED_LABEL_KEY}=${HKB_TRUSTED_SHA}" -t "${HKB_TEST_IMAGE}" . ) \
    || die '受信任测试镜像构建失败：请检查 Docker Hub 可达性与磁盘余量（本脚本不会回退到用候选构建，也不会改用宿主机执行测试）'
  BUILT_LABEL="$(docker image inspect "${HKB_TEST_IMAGE}" \
    --format "{{index .Config.Labels \"${TRUSTED_LABEL_KEY}\"}}" 2>/dev/null || true)"
  [[ "${BUILT_LABEL}" == "${HKB_TRUSTED_SHA}" ]] \
    || die "镜像标签为 '${BUILT_LABEL}'，与 HKB_TRUSTED_SHA 不一致：拒绝继续"
  info '受信任测试镜像构建完成并已打标签'
fi

if sudo -u "${BUILDER_USER}" -H docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  info "${BUILDER_USER} 可以访问 docker（新会话已带上 docker 组）"
else
  warn "${BUILDER_USER} 目前无法访问 docker：请确认 usermod -aG docker 已生效（重新登录会话后即可）"
fi

# -----------------------------------------------------------------------------
# 8. 后续步骤
# -----------------------------------------------------------------------------
cat <<'NEXT'

================================================================================
构建机安装完成。以下必须由人工完成：
================================================================================
1) 把阿里云控制器的公钥加入构建机（内容见 deploy/sg/authorized_keys.snippet）：
     install -d -m 0700 -o hkbuild -g hkbuild /opt/huakangos-builder/.ssh
     touch /opt/huakangos-builder/.ssh/authorized_keys
   把 snippet 里 (a) 那一条（restrict,command="/opt/huakangos-builder/bin/hk_builder" ...）
   追加进去，然后：
     chown -R hkbuild:hkbuild /opt/huakangos-builder/.ssh
     chmod 700 /opt/huakangos-builder/.ssh
     chmod 600 /opt/huakangos-builder/.ssh/authorized_keys
   注意：这里放的是「阿里云控制器的公钥」，私钥永远留在阿里云。

2) 登记构建机的 GitHub deploy key（用于 git push 候选分支与快进主分支）：
     sudo -u hkbuild -H ssh-keygen -t ed25519 -a 100 -N '' \
       -C 'huakangos-builder@binance-bot' \
       -f /opt/huakangos-builder/.ssh/github_deploy_ed25519
     cat /opt/huakangos-builder/.ssh/github_deploy_ed25519.pub
   把公钥登记为专用仓库的 Deploy Key 并允许写入；私钥不要复制到任何其它机器。
   注册完成后重新运行本脚本，它会克隆可信检出并构建受信任测试镜像。

3) 在阿里云控制器上预置本机主机密钥（控制器用 StrictHostKeyChecking=yes）：
   本机 sshd 主机公钥（请人工核对指纹后把 IP + 下面这行写进
   /opt/huakangos/.ssh/known_hosts）：
NEXT
for pub in /etc/ssh/ssh_host_ed25519_key.pub /etc/ssh/ssh_host_rsa_key.pub /etc/ssh/ssh_host_ecdsa_key.pub; do
  [[ -f "${pub}" ]] || continue
  printf '     %s  %s\n' "$(cut -d' ' -f1 <"${pub}")" "$(cut -d' ' -f2 <"${pub}")"
  ssh-keygen -lf "${pub}" | sed 's/^/     指纹：/'
done
cat <<'NEXT'

4) 从阿里云验证这条受限通道（动词由 Python 从 $SSH_ORIGINAL_COMMAND 解析）：
     sudo -u huakang -H ssh -i /opt/huakangos/.ssh/sg_builder_ed25519 \
       -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes \
       hkbuild@207.148.126.193 status

5) 日常候选构建由控制器经 candidate 动词触发；改动 HKB_TRUSTED_SHA 后重新运行本脚本
   即按新基线重建测试镜像。维护窗口（Asia/Shanghai 22:00-06:00，并在 00:01/04:01 前后
   让行）与本机系统时区 Etc/UTC 无关：window.py 全程使用显式时区换算。
   最后：本机还跑着生产量化服务，任何操作都不要再重启系统或改动它们的单元。
================================================================================
NEXT

info '全部步骤完成'