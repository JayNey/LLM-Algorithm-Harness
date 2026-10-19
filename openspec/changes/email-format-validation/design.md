# Design: 邮箱格式校验

`validateEmail` 在长度 3–254 之外，使用与 `RegisterInput` / `ProfileUpdate` 相同的规则：`^[^\s@]+@[^\s@]+\.[^\s@]+$`。失败文案保持「请输入有效邮箱」。

注册和资料都调用这个函数，因此两处一起收紧。登录只校验身份非空且不超过 254 个字符。

需要拒绝的例子：`a.b@c`（点不在域名）、`a@b.`（点后没有域名字符）、`a @b.com`、`a@b@c.com`。`ada@example.com` 仍然通过。
