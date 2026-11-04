## ADDED Requirements

### Requirement: 评估检查点与业务结果恢复一致
系统 SHALL 在评估恢复时将已确认的检查点终态单元幂等补齐到 SQL，按稳定题目×策略身份更新结果、计数及费用，同一单元重复恢复不得重复计费。对账 SHALL 在预算检查及新单元执行之前完成；已确认完成的模型单元不得重新调用。最终完成 SHALL 具有覆盖全部预期单元的 SQL 结果及 complete 发布快照和导出。

#### Scenario: 文件提交后 SQL 提交前 worker 丢失
- **WHEN** 文件已确认单元完成而 SQL 尚未提交，worker 丢失后重新投递
- **THEN** 恢复补齐结果及费用，仅执行未确认的单元

#### Scenario: SQL 已提交后重复恢复
- **WHEN** SQL 结果和费用已提交但 worker 随后丢失，包括最后一个单元完成后
- **THEN** 重复对账不增加费用或重复执行，全部完成后发布 complete 结果快照

#### Scenario: 文件提交前退出
- **WHEN** 单元尚未确认落盘时 worker 退出
- **THEN** 恢复可以重试该单元，结果数量和费用保持一致
