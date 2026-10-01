# PATCH-M8-4-BOUTIQUE-SOURCE-BOUNDARY-01

2026-10-01，M8.1。member-boutique01的精品首次场景0.17秒/零动作失败“证据不能在被测源码内”。只读核对发现候选以 Path(__file__).parents[2] 当源码，而外置 scripts 下该祖先实际为全部browser-click父目录，合法external evidence当然位于其内。真实manifest.source_root是同run/source，库/evidence位于其外；不是隔离破坏。

全部关联自动、manual03/04、setup都已退出后，允许只改 tests/browser_click/boutique_business.py 的该边界为 manifest.source_root.resolve()。同轮runtime/database、五路径、实际passed父源与完整provenance/source/script/catalog守卫保持。原工作区如另作边界必须使用provenance实际路径，不靠脚本祖目录；不增加兼容默认或免检。AST/原接口短审后全新九场景同序原UI复验，精品先于会期。旧失败六项均未执行，不记通过。
