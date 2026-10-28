-- 门户站申请登记（D1 数据库 hearsay-portal）
CREATE TABLE IF NOT EXISTS applications (
  email TEXT PRIMARY KEY,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT '',
  verified INTEGER NOT NULL DEFAULT 0
);
