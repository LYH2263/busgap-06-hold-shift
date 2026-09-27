import os

# 测试不依赖 Postgres：在导入应用模块前把引擎指向 sqlite（各测试再自行覆盖）
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SEED_ON_EMPTY", "false")
