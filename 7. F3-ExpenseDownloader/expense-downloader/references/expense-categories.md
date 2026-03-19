# 费用分类规则定义

> 本文件定义 Expense 材料的分类规则，供 classify_expense.py 和 Agent 使用。

---

## 分类体系

| 类别 ID | 图标 | 中文名 | 英文名 | 目录名 |
|---------|------|--------|--------|--------|
| transport_didi | 🚗 | 网约车 | Ride-hailing | transport/didi/ |
| transport_flight | ✈️ | 航空 | Flight | transport/flight/ |
| transport_train | 🚄 | 火车 | Train | transport/train/ |
| transport_other | 🚌 | 其他交通 | Other Transport | transport/other/ |
| accommodation | 🏨 | 住宿 | Accommodation | accommodation/ |
| dining | 🍽️ | 餐饮 | Dining | dining/ |
| telecom | 📱 | 通讯 | Telecom | telecom/ |
| office | 💻 | 办公 | Office | office/ |
| other | 📋 | 其他 | Other | other/ |

---

## 分类规则（按优先级）

### 规则 1: 发件人精确匹配（最高优先级）

| 发件人模式 | 分类 |
|-----------|------|
| `didifapiao@*` | transport_didi |
| `*@t3go.cn` | transport_didi |
| `*@caocao*.com` | transport_didi |
| `10086@139.com` | telecom |
| `*@chinaunicom.cn` | telecom |
| `*@189.cn` | telecom |
| `mhrs.*.gsm@marriott.com` | accommodation |
| `*@hilton.com` | accommodation |
| `*@hyatt.com` | accommodation |
| `*@ihg.com` | accommodation |
| `*@accor.com` | accommodation |
| `Invoice@store.timschina.com` | dining |
| `*@starbucks*` | dining |
| `*@mcd*.com` | dining |

### 规则 2: 邮件主题关键词匹配

| 关键词 | 分类 |
|--------|------|
| 行程单, 航班, 机票, flight, boarding | transport_flight |
| 火车票, 高铁, 动车, 12306 | transport_train |
| 打车, 出行, 行程, 网约车 | transport_didi |
| 酒店, hotel, 水单, folio, 住宿, 入住 | accommodation |
| 餐饮, 餐厅, restaurant, 外卖, 美团 | dining |
| 话费, 流量, 通讯, 月结, 账单(移动/联通/电信) | telecom |
| 办公, 文具, 打印, 耗材 | office |

### 规则 3: 文件名模式匹配

| 文件名模式 | 分类 |
|-----------|------|
| `*滴滴*`, `*DiDi*` | transport_didi |
| `*行程单*`, `*itinerary*` | transport_flight |
| `*火车票*`, `*12306*` | transport_train |
| `*水单*`, `*folio*`, `*hotel*` | accommodation |
| `*中国移动*`, `*China Mobile*` | telecom |

### 规则 4: Agent 语义判断（兜底）

当以上规则均无法匹配时，由 Agent 根据邮件上下文综合判断。
无法判断的归入 `other/`。

---

## 文件命名规范

```
{YYYYMMDD}_{供应商}_{类型}.pdf
```

示例:
- `20260115_滴滴出行_电子发票.pdf`
- `20260118_Marriott_水单.pdf`
- `20260201_中国移动_话费发票.pdf`

日期来源优先级:
1. 邮件日期（最可靠）
2. 文件名中的日期
3. 下载日期（兜底）

---

## 负面过滤（排除非 Expense 邮件）

以下关键词出现在主题中时，跳过该邮件:

```
退票, 退款, 还款提醒, 预订确认, 对账单, 周报, 月报,
unsubscribe, 广告, 促销, 优惠券, 积分, 会员, 升级,
密码, 验证码, 安全提醒, 登录, 注册
```
