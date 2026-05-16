# DONE
1. 支持添加新的 tool (仅 litellm model)
2. Trajectory format bump: `mini-swe-agent-1.1` → `mini-swe-agent-1.1-junkai`
   - 原因：`extra.actions[*]` 和 tool observation 的 `extra` 各新增了 `tool_name` 字段，schema 不再与 upstream 1.1 兼容。
   - 用 `-junkai` 后缀而非 1.2，避免跟上游未来正式 bump 到 1.2 撞号。
   - 下游分析/训练脚本可按 `trajectory_format.endswith("-junkai")` 或字符串相等判断；不带后缀的轨迹默认 `tool_name = "bash"`，带后缀的可直接读字段。


# TODO
1. 检查一下是否有工具调用无法获得良好的反馈给 LLM


1. yaml 里面的 tool 相关的部分要改 (error 那里也有)
2. 整个代码仓库里面查一下，关于工具调用的部分，希望日志什么的也能打印




# Tool management

1. 添加新 tool: 
在 config = yaml 之前，
```
# 定义一个类，然后加到 BUILTIN：
class MyTool:
    name = "my_tool"
    schema = {...}
    def validate(self, args): ...
    def to_command(self, args): ...

BUILTIN["my_tool"] = MyTool
```

2. 在 YAML 的`model.tools` 下列出 builtin tool 名字：
```yaml
model:
  tools: [bash, submit]   # 默认
```



# 不管了
2. 仅支持 LitellmModel（PortkeyModel / RequestyModel / OpenRouterModel 暂未迁移）
3. 多工具组合尚无集成测试