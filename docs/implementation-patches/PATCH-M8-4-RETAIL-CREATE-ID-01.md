# PATCH-M8-4-RETAIL-CREATE-ID-01

2026-10-01，M8.1，所有关联验证已退出。PATCH33 Retail作者abc8b721独立只读窄审发现两处 MF.submit_created 缺原必填 body_key；原Retail及Bundle销售POST都返回顶层id，实际首次原提交前会TypeError。仅新 tests/browser_click/retail_remaining_business.py 这两调用补 body_key=("id",)，不改通用helper默认值或查latest找原单。作者原SHA与此次根差异分别留证，继续审阅/全新实际点击待测，未记通过。
