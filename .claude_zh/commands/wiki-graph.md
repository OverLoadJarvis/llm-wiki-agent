构建 LLM Wiki 知识图谱。

用法：/wiki-graph

首先尝试运行：python tools/build_graph.py --open

如果失败（缺少依赖），手动构建图谱：

1. 使用 Grep 在 wiki/ 中的每个文件中查找所有 [[wikilinks]]
2. 构建节点列表：每个 wiki 页面一个节点，id=相对路径，label=标题，类型来自 frontmatter
3. 构建边列表：每个 [[wikilink]] 一条边，标记为 EXTRACTED
4. 推断页面之间未被 wikilinks 捕获的额外隐式关系 — 标记为 INFERRED 并给出置信度分数（0.0–1.0）；低置信度的标记为 AMBIGUOUS
5. 写入 graph/graph.json，格式为 {nodes, edges, built: today}
6. 写入 graph/graph.html 作为自包含的 vis.js 页面（节点按类型着色，边按类型着色，可交互，可搜索）

构建完成后，总结：节点数、边数、按类型分类的统计，以及连接最多的节点（中心节点）。

追加到 wiki/log.md：## [today's date] graph | Knowledge graph rebuilt