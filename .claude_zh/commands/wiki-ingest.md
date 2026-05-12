将源文档摄取到 LLM Wiki 中。

用法：/wiki-ingest $ARGUMENTS

$ARGUMENTS 应为 raw/ 中的文件路径，例如 `raw/articles/my-article.md`

严格按照 CLAUDE.md 中定义的摄取工作流执行：
1. 读取给定路径的源文件
2. 读取 wiki/index.md 和 wiki/overview.md 获取当前上下文
3. 写入 wiki/sources/<slug>.md（按照 CLAUDE.md 的源页面格式）
4. 更新 wiki/index.md — 在 Sources 下添加新条目
5. 更新 wiki/overview.md — 如有必要修订综合内容
6. 创建/更新实体页面（wiki/entities/）用于关键人物、公司、项目
7. 创建/更新概念页面（wiki/concepts/）用于关键想法和框架
8. 标记与现有 wiki 内容的任何矛盾
9. 追加到 wiki/log.md：## [today's date] ingest | <Title>

完成所有写入后，总结：添加了什么内容，创建或更新了哪些页面，以及发现的任何矛盾。