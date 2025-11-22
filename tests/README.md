# 测试说明

## 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行所有测试
```bash
python -m pytest tests/ -v
```

### 运行带覆盖率的测试
```bash
python -m pytest tests/ --cov=. --cov-config=.coveragerc --cov-report=term-missing
```

### 生成HTML覆盖率报告
```bash
python -m pytest tests/ --cov=. --cov-config=.coveragerc --cov-report=html
# 报告会生成在 htmlcov/ 目录
```

## 测试文件说明

### test_models.py
测试数据模型（Concept, Memory, Connection）

**运行**: `python -m pytest tests/test_models.py -v`

### test_config.py
测试配置管理系统

**运行**: `python -m pytest tests/test_config.py -v`

### test_memory_graph.py
测试记忆图数据结构

**运行**: `python -m pytest tests/test_memory_graph.py -v`

### test_batch_extractor.py
测试批量记忆提取器

**运行**: `python -m pytest tests/test_batch_extractor.py -v`

### test_integration.py
集成测试，测试多个模块协作

**运行**: `python -m pytest tests/test_integration.py -v`

## 测试选项

### 只运行特定测试
```bash
# 运行特定的测试类
python -m pytest tests/test_models.py::TestConcept -v

# 运行特定的测试方法
python -m pytest tests/test_models.py::TestConcept::test_concept_creation -v
```

### 并行运行测试
```bash
pip install pytest-xdist
python -m pytest tests/ -n auto
```

### 只运行失败的测试
```bash
python -m pytest tests/ --lf
```

### 详细输出
```bash
python -m pytest tests/ -vv
```

## 覆盖率目标

- **最低要求**: 95%
- **当前覆盖率**: 99.13%

## 测试框架

- **单元测试框架**: pytest
- **覆盖率工具**: pytest-cov
- **异步测试**: pytest-asyncio
- **Mock工具**: unittest.mock

## 注意事项

1. 所有测试都应该是独立的，不依赖执行顺序
2. 使用 setUp 和 tearDown 方法进行测试准备和清理
3. 使用 Mock 对象避免依赖外部服务
4. 测试应该快速执行（< 1秒/测试）

## 贡献测试

添加新测试时：
1. 遵循现有的命名约定（test_*）
2. 添加清晰的文档字符串
3. 确保测试覆盖边界情况
4. 运行所有测试确保没有破坏现有功能
5. 检查覆盖率是否达标
