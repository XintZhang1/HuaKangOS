# 门店价格与赠品定向验证

仅使用当前源码白名单镜像和新建合成 SQLite，不复制业务库、配置、密钥或客户表格。数据库、上传文件、日志及结果保存在仓库外。Python 网络套接字禁用；真实 FastAPI 路由经进程内 ASGI 调用，保留登录、Cookie、CSRF、门店及岗位权限守卫，不调用真实模型。

```sh
python -m pip install -r requirements.txt pytest==8.4.2
python tests/record_pricing/run_isolated.py --output /tmp/huakangos-pricing-check-new
```

每次 `--output` 须为新的仓库外目录。结果见 `evidence/result.json`、`junit.xml`、`python.log` 和逐文件 `source-manifest.json`；镜像期间源码变化会拒绝执行。

覆盖真实 XLSX 上传、空/过大/损坏/错误类型/非法文件名拒绝、CSRF/上传权限、识别失败保留原件且未发布、人工确认后实际发布、上传者校验、赠品 CSV 预览/成本权限、同品牌共享与异品牌隔离、金额投影、合同赠品保存/取消/回显、目录更新后冻结原批次及私有合同权限。赠品总成本预算与超限标记保持既有规则。

该检查使用 ORM 创建合成数据库，不宣称迁移验收、真实 DeepSeek 识别、生产验证或员工验收。GitHub 仅执行这些非浏览器检查；原生浏览器验证另行在本地隔离实例执行。

本地原生浏览器定向检查：在同一独立 Python 环境追加 Playwright，指定已安装的 Chromium/Chrome 路径。脚本从当前源码建立外部镜像，迁移全新合成数据库并创建随机账号，通过原页面登录、上传、人工确认发布、预填及保存合同。

```sh
python -m pip install playwright==1.56.0
python tests/record_pricing/browser_check.py --browser /usr/bin/chromium --output /tmp/huakangos-pricing-browser-new
```

浏览器检查包含独立折叠/展开、资料与合同草稿保持、错误文件及识别不可用反馈、真实手工核对发布、跨搜索选择/数量/取消、保存刷新回显、销售上传权限和跨店合同隔离。截图与实际执行清单保存在该次外部 `evidence/`，源码与脚本副本分别保留。识别服务故意未配置，不将人工恢复发布称为真实模型识别成功；不对既有数据库执行迁移或写入。
