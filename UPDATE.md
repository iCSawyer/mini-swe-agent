# Tool management

## 配置使用
在 `model.tools` 下列出 builtin tool 名字：
```yaml
model:
  tools: [bash]
添加新 tool
在 src/minisweagent/models/utils/tools.py 里定义一个类，然后加到 BUILTIN：


class MyTool:
    name = "my_tool"
    schema = {...}
    def validate(self, args): ...
    def to_command(self, args): ...

BUILTIN["my_tool"] = MyTool
当前限制
仅支持 LitellmModel（PortkeyModel / RequestyModel / OpenRouterModel 暂未迁移）
多工具组合尚无集成测试