# 主要国家/地区最小货币单位对照表

> 本文件隶属于 `dev-logic-architect` SKILL，供 `flow-money-field.md`「💰 货币金额字段设计规则」章节引用。
> 上级文档：`../SKILL.md`

> **数据来源**: ISO 4217 标准 + 各国央行公告。最小单位指"实际流通的最小货币细分单位",`小数位`指 ISO 4217 标准小数位指数(`10^N` = 1 主币单位包含的最小单位数)。

## 🏛️ 主要经济体(G7 / 金砖 / G20 核心)

| 国家/地区 | ISO 代码 | 主币单位 | 最小单位 | 换算关系 | 小数位 | 备注 |
| :- | :-: | :- | :- | :- | :-: | :- |
| 中国大陆 | CNY | 元(Yuan) | 分(Fen) | 1 元 = 100 分 | 2 | 人民币 RMB |
| 美国 | USD | dollar | cent | 1 USD = 100 cents | 2 | 全球结算主货币 |
| 欧元区(德/法/意/西/荷等 20 国) | EUR | euro | cent | 1 EUR = 100 cents | 2 | 第二大国际货币 |
| 日本 | JPY | 円(yen) | 円(yen) | **1 yen = 1 yen** | **0** | **无小数,主币即最小单位** |
| 英国 | GBP | pound | penny(pence) | 1 GBP = 100 pence | 2 | — |
| 印度 | INR | rupee | paisa | 1 INR = 100 paise | 2 | 实际 paise 几乎不流通 |
| 俄罗斯 | RUB | ruble | kopeck | 1 RUB = 100 kopecks | 2 | — |
| 巴西 | BRL | real | centavo | 1 BRL = 100 centavos | 2 | — |
| 加拿大 | CAD | dollar | cent | 1 CAD = 100 cents | 2 | 已停铸 1 cent 硬币但记账仍用 |
| 澳大利亚 | AUD | dollar | cent | 1 AUD = 100 cents | 2 | — |
| 韩国 | KRW | won(원) | won | **1 KRW = 1 KRW** | **0** | **无小数,jeon 已停用** |
| 墨西哥 | MXN | peso | centavo | 1 MXN = 100 centavos | 2 | — |
| 土耳其 | TRY | lira | kuruş | 1 TRY = 100 kuruş | 2 | — |
| 沙特阿拉伯 | SAR | riyal | halala | 1 SAR = 100 halalas | 2 | — |
| 阿根廷 | ARS | peso | centavo | 1 ARS = 100 centavos | 2 | 高通胀,实务多直接用 peso |
| 南非 | ZAR | rand | cent | 1 ZAR = 100 cents | 2 | — |
| 印度尼西亚 | IDR | rupiah | sen | 1 IDR = 100 sen | 2 | sen 实际不流通,记账仍按 ISO |

## 👥 人口大国 / 新兴市场(补充)

| 国家/地区 | ISO 代码 | 主币单位 | 最小单位 | 换算关系 | 小数位 | 备注 |
| :- | :-: | :- | :- | :- | :-: | :- |
| 巴基斯坦 | PKR | rupee | paisa | 1 PKR = 100 paisa | 2 | — |
| 孟加拉国 | BDT | taka | poisha | 1 BDT = 100 poisha | 2 | — |
| 尼日利亚 | NGN | naira | kobo | 1 NGN = 100 kobo | 2 | — |
| 越南 | VND | đồng | đồng | **1 VND = 1 VND** | **0** | **无小数,xu 已停用** |
| 菲律宾 | PHP | peso | centavo(sentimo) | 1 PHP = 100 centavos | 2 | — |
| 埃及 | EGP | pound | piastre | 1 EGP = 100 piastres | 2 | — |
| 埃塞俄比亚 | ETB | birr | santim | 1 ETB = 100 santim | 2 | — |
| 泰国 | THB | baht | satang | 1 THB = 100 satang | 2 | — |
| 马来西亚 | MYR | ringgit | sen | 1 MYR = 100 sen | 2 | — |
| 伊朗 | IRR | rial | dinar | 1 IRR = 100 dinars | 2 | dinar 实务不流通 |
| 哥伦比亚 | COP | peso | centavo | 1 COP = 100 centavos | 2 | 拉美第 4 大经济体,人口 5100 万 |
| 秘鲁 | PEN | sol | céntimo | 1 PEN = 100 céntimos | 2 | 拉美第 6 大经济体 |
| 乌克兰 | UAH | hryvnia | kopiyka | 1 UAH = 100 kopiykas | 2 | 东欧外包/跨境业务常见 |
| 哈萨克斯坦 | KZT | tenge | tïın | 1 KZT = 100 tïın | 2 | 中亚最大经济体 |
| 摩洛哥 | MAD | dirham | centime | 1 MAD = 100 centimes | 2 | 北非门户 |
| 肯尼亚 | KES | shilling | cent | 1 KES = 100 cents | 2 | 东非金融中心,移动支付 M-Pesa 发源地 |

## 💼 国际化 / 金融中心常用货币

| 国家/地区 | ISO 代码 | 主币单位 | 最小单位 | 换算关系 | 小数位 | 备注 |
| :- | :-: | :- | :- | :- | :-: | :- |
| 香港 | HKD | dollar | cent | 1 HKD = 100 cents | 2 | 离岸人民币重要交易市场 |
| 新加坡 | SGD | dollar | cent | 1 SGD = 100 cents | 2 | — |
| 中国台湾 | TWD | 元(yuan) | 分(fen) | 1 TWD = 100 fen | 2 | 实际不流通 fen,记账仍按 ISO |
| 中国澳门 | MOP | pataca | avo | 1 MOP = 100 avos | 2 | — |
| 瑞士 | CHF | franc | rappen / centime | 1 CHF = 100 rappen | 2 | 避险货币 |
| 新西兰 | NZD | dollar | cent | 1 NZD = 100 cents | 2 | — |
| 挪威 | NOK | krone | øre | 1 NOK = 100 øre | 2 | øre 实物停铸,记账仍用 |
| 瑞典 | SEK | krona | öre | 1 SEK = 100 öre | 2 | öre 实物停铸,记账仍用 |
| 丹麦 | DKK | krone | øre | 1 DKK = 100 øre | 2 | — |
| 阿联酋 | AED | dirham | fils | 1 AED = 100 fils | 2 | 中东金融中心(迪拜) |
| 以色列 | ILS | shekel | agora | 1 ILS = 100 agorot | 2 | — |
| 波兰 | PLN | zloty | grosz | 1 PLN = 100 groszy | 2 | — |
| 捷克 | CZK | koruna | haléř | 1 CZK = 100 haléřů | 2 | haléř 实际停用,记账仍按 ISO |
| 匈牙利 | HUF | forint | fillér | **1 HUF = 1 HUF** | **0** | **fillér 已废除,实务无小数** |
| 冰岛 | ISK | króna | eyrir | **1 ISK = 1 ISK** | **0** | **eyrir 已废除** |

## ⚠️ 特殊小数位货币(易踩坑,重点提醒)

**0 位小数(主币即最小单位,整数存储时 ÷1):**

- `JPY` 日本日元 / `KRW` 韩国韩元 / `VND` 越南盾 / `HUF` 匈牙利福林 / `ISK` 冰岛克朗 / `CLP` 智利比索 / `PYG` 巴拉圭瓜拉尼 / `RWF` 卢旺达法郎 / `XOF`/`XAF` 西非/中非法郎 / `UGX` 乌干达先令 / `XPF` 太平洋法郎

> **关于 IDR(印尼盾)**: ISO 4217 标 2 位(主币 = 100 sen),但 sen 实务已不流通,部分系统按 0 位处理;接入印尼业务前需与对接方明确按 ISO(×100)还是按实务(×1)存储,并在 A.4 `CurrencyCode` 字典中显式标注。

**3 位小数(1 主币 = 1000 最小单位,中东第纳尔系):**

- `KWD` 科威特第纳尔 / `BHD` 巴林第纳尔 / `JOD` 约旦第纳尔 / `OMR` 阿曼里亚尔 / `TND` 突尼斯第纳尔 / `LYD` 利比亚第纳尔 / `IQD` 伊拉克第纳尔

> **踩坑示例**: 用户输入 100 科威特第纳尔,**正确**存储为 `100000`(单位 fils);若按常规 ×100 处理则少存 10 倍,直接造成 90% 资损。
