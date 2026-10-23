# 修复方案

保存使用 a+ 非破坏性打开，seek(0) 后获取现有 exclusive_lock（保证 Windows 锁首字节），在锁内 seek(0)、truncate、写入 JSON/换行、flush。读取在 JSON 解析期间获取同一 exclusive_lock，保留原异常处理。Unix 等待锁；Windows 沿用现有非阻塞锁语义，锁冲突抛 OSError，保存继续按既有次数重试。

回归测试覆盖加锁前旧内容完整、加锁失败保留历史、解锁前可见完整内容、短内容覆盖无残留及 Unix 读写/写写并发窗口。首次创建仍允许不存在文件返回空历史，不提供崩溃恢复或读改写合并保证。
