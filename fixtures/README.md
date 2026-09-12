# fixtures/ —— 探针夹具

夹具是「角色收到的最后一份上下文」：一个 messages 数组，探针把最后一条 user 换成本轮要测的问题，system 段与历史保持不动。这样 before / after 两臂的差异只可能来自被改的那一层。

## 这里的占位夹具

仓库自带五份占位夹具（每角色一份），system 为空、只有一条说明性的 user。它们的用途是让探针**开箱可跑**：

```bash
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic \
    --registry --cats 通用场景 --runs 3
```

`--assemble` 会用 `idiolect.assemble` 按本轮 user 现场装配四层 system。**不加这个参数**，模型收到的是空 system，回复会退化成通用助手腔，此时测的是「没有角色 prompt 的模型」——所以探针在 system 段短于 1000 字符时会直接报错退出。

## 换成你自己的真实 dump

真实运行时 dump 出来的 messages 数组（含当天记忆、日程、世界状态）直接放进这个目录，命名 `messages_<角色>_<时间戳>.json`，探针会取最新的那份，占位夹具自动让位。

要另建一套夹具做 A/B，复制一份改名即可；探针按角色名匹配，不同角色的夹具互不干扰。

## 夹具可测性的两个条件

1. **有可指代的上文**。像「你刚才那句什么意思」这种场景，需要上文里真有一句话可以指；上下文为空的夹具测不了这个场景，得到的分数不能当证据。
2. **system 段完整**。要么夹具自带真实 prompt，要么加 `--assemble`。两者都没有时测到的是裸模型。

夹具的构造与坑见 `docs/04-evaluation.md` 第 6 节。
