对 LLM Wiki 进行健康检查以查找问题。

用法：/wiki-lint

按照 CLAUDE.md 中定义的检查工作流执行：

结构检查（使用 Grep 和 Glob 工具）：
1. 孤立页面 — 没有其他页面指向的 [[wikilinks]] 的 wiki 页面
2. 断开的链接 — [[WikiLinks]] 指向不存在的页面
3. 缺失的实体页面 — 在 3 个以上页面中引用但没有自己页面的名称

语义检查（读取并分析页面内容）：
4. 矛盾内容 — 页面之间冲突的主张
5. 过时摘要 — 在新源改变情况后未更新的页面
6. 数据缺口 — wiki 无法回答的重要问题；建议查找特定来源

输出结构化的 markdown 检查报告。最后询问用户是否要保存到 wiki/lint-report.md。

追加到 wiki/log.md：## [today's date] lint | Wiki health check