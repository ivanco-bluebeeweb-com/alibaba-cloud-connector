# Alibaba Cloud Connector — Connector Discovery

**Дата discovery:** 2026-08-24
**Vikunja task:** #2473 ([App Development] Alibaba Cloud Connector, BBW Imperal Apps)
**Статус:** Ярусы 1-3 определены по прецеденту AWS/Azure/GCP/OCI/DigitalOcean Connector.
Пользователь явно заявил "приступай к разработке всех приложений
Гипермасштабные облака (IaaS/PaaS) категории" — заранее заявленное
решение объёма ("максимум"), освобождает от повторного вопроса в §7.

Последний член категории "Гипермасштабные облака (IaaS/PaaS)" из
`Docs/session-notes/NEXT_12_CATEGORIES_RESEARCH.md` — после этого
приложения категория закрыта целиком (AWS/Azure/GCP/OCI уже сделаны).

---

## 1. Целевой сервис и источники

Alibaba Cloud — ключевой мост для enterprise-клиентов с операциями в
Азии (~4% доли рынка, Synergy Q2'25). RPC-style REST API, множество
отдельных сервисов на разных поддоменах `<service>.<region>.aliyuncs.com`.

Источники (прочитаны 2026-08-24):
- `alibabacloud.com/help/en/sdk/product-overview/rpc-mechanism` — полное
  описание V2 RPC signature (алгоритм, псевдокод, рабочий Python-пример)
- `alibabacloud.com/help/en/ecs/developer-reference/api-ecs-2014-05-26-overview`
  — полный каталог ECS API операций (Instance/Image/Disk/Snapshot/
  Networking/SecurityGroup/KeyPair и т.д.)

## 2. Auth-модель — RPC-style Signature V2 (HMAC-SHA1), СВОЙ АЛГОРИТМ, НЕ AWS SigV4

Alibaba Cloud использует собственную схему подписи запросов, концептуально
похожую на AWS SigV4 (подпись каждого запроса общим секретом), но с
другим алгоритмом и другой канонизацией:

**Credential:** AccessKey ID + AccessKey Secret (создаются в RAM console).

**Алгоритм подписи (V2, RPC-style):**
1. Собрать все параметры (общие + специфичные для операции), КРОМЕ
   `Signature`, отсортировать по ключу в алфавитном порядке.
2. URL-encode каждый ключ/значение по RFC 3986 (буквы/цифры/`-_.~` не
   кодируются, пробел -> `%20`, `*` -> `%2A`, `~` НЕ кодируется —
   особые правила, отличные от стандартного `urllib.parse.quote`).
3. Собрать `CanonicalizedQueryString` join'ом `key=value` через `&`
   (в том же отсортированном порядке).
4. Собрать `stringToSign = HTTPMethod + "&" + encode("/") + "&" + encode(CanonicalizedQueryString)`.
5. `signature = Base64(HMAC_SHA1(AccessKeySecret + "&", stringToSign))`.
6. URL-encode подпись и добавить как параметр `Signature` в финальный URL.

**Обязательные общие параметры на каждый запрос:** `AccessKeyId`,
`Action`, `Version` (у каждого сервиса своя дата-версия API, например
ECS = `2014-05-26`), `Format=JSON`, `SignatureMethod=HMAC-SHA1`,
`SignatureVersion=1.0`, `SignatureNonce` (случайная строка, анти-replay),
`Timestamp` (ISO 8601, `yyyy-MM-ddTHH:mm:ssZ`, действителен 31 минуту).

**Почему нельзя переиспользовать `oci_client.py` (RSA) или `aws_sigv4.py`
(SigV4) напрямую:** другой алгоритм (HMAC-SHA1 против RSA-SHA256/
HMAC-SHA256), другая канонизация (query string vs canonical request с
заголовками), другой набор служебных параметров. Нужен отдельный
`alibaba_client.py` с этим конкретным алгоритмом.

**Единственная критичная деталь совместимости:** URL-encode правила
Alibaba Cloud ТОЧНО совпадают с `urllib.parse.quote(safe="~")` плюс
замена `+`->`%20` и `*`->`%2A` — Python `urllib.parse.quote` уже не
кодирует `~` по умолчанию с `safe="~"`, но кодирует `*` и не трогает
`+` (raw `+` остаётся как `+`, а не `%20`) — обе замены нужно делать
вручную после `quote()`.

## 3. Регионы и эндпоинты

Формат: `https://<service-code>.<region-id>.aliyuncs.com`, например
`ecs.cn-hangzhou.aliyuncs.com`, `oss-cn-hangzhou.aliyuncs.com` (OSS —
особый формат с дефисом, не точкой перед регионом). Международные
регионы (`ap-southeast-1`, `us-east-1`, `eu-central-1`) и китайские
(`cn-hangzhou`, `cn-beijing`, `cn-shanghai`) используют один и тот же
домен `aliyuncs.com` — нет отдельного домена для Китая, в отличие от
некоторых предположений до discovery. RegionId передаётся как
операционный параметр запроса, а не меняет базовый домен подписи.

## 4. Домен покрытия (по прецеденту AWS/Azure/GCP/OCI/DigitalOcean)

| Сервис | Alibaba Cloud API | Аналог у других облаков |
|---|---|---|
| Elastic Compute Service (ECS) | `ecs.<region>.aliyuncs.com`, версия `2014-05-26` | EC2 / VM / Compute Engine / Compute instance / Droplet |
| Object Storage Service (OSS) | `oss-<region>.aliyuncs.com`, отдельный S3-совместимый REST (не RPC-style!) | S3 / Blob / Cloud Storage / Spaces |
| ApsaraDB (RDS) | `rds.<region>.aliyuncs.com` | RDS / Cloud SQL / Managed Database |
| Container Service for Kubernetes (ACK) | `cs.<region>.aliyuncs.com`, read-only | EKS/AKS/GKE/DOKS (read-only) |
| Resource Access Management (RAM) | `ram.aliyuncs.com` (глобальный, без региона), read-only | IAM |
| CloudMonitor | `metrics.<region>.aliyuncs.com` | CloudWatch/Monitor/Cloud Monitoring/Monitoring alerts |
| BSS OpenAPI (Billing) | `business.aliyuncs.com` (глобальный) | Cost Explorer/Cost Management/Billing |

OSS ВАЖНО: в отличие от остальных сервисов (RPC-style с Signature V2),
OSS использует СВОЙ отдельный S3-совместимый REST API с другой схемой
подписи (заголовок `Authorization: OSS <AccessKeyId>:<signature>`,
канонизация похожая на AWS S3 legacy V2, НЕ RPC-style). Это отдельный
крипто-путь внутри одного клиента — как AWS Connector уже различает
основной SigV4 и S3 host-style. Подтверждено паттерном у DigitalOcean
(Spaces — отдельная auth) и AWS (S3 — тот же SigV4, но другой host).

## 5. Ярусы

**Ярус 1 (MVP):** connect_alibaba_cloud (AccessKey ID + Secret + опц.
default region), disconnect_alibaba_cloud, list_connections,
list_virtual_machines / get_virtual_machine (ECS DescribeInstances/
DescribeInstanceAttribute), start/stop/restart_virtual_machine
(StartInstance/StopInstance/RebootInstance).

**Ярус 2:** list_storage_accounts (OSS ListBuckets — отдельный клиент),
list_sql_databases (RDS DescribeDBInstances), list_kubernetes_clusters
(ACK DescribeClustersV1, read-only), list_iam_users (RAM ListUsers,
read-only), list_metric_alerts (CloudMonitor DescribeMetricRuleList).

**Ярус 3 (value-add):** get_cloud_overview (агрегированная сводка:
ECS running/stopped + OSS buckets + RDS + ACK + баланс счёта),
query_costs (BSS OpenAPI QueryAccountBalance / DescribeInstanceBill).

## 6. Известные подводные камни

1. URL-encode ПОЧТИ как `urllib.parse.quote`, но не идентично (`+`,
   `*`, `~` требуют ручных замен после стандартного quote) — если не
   исправить, подпись будет ВСЕГДА невалидна для параметров с этими
   символами (например Base64-содержимое, пробелы в именах).
2. `Timestamp` действителен только 31 минуту — часы сервера должны
   быть синхронизированы (обычно не проблема на стороне Imperal
   backend, но стоит логировать факт истечения отдельно от auth-ошибки).
3. OSS — полностью отдельная auth-схема внутри одного коннектора, не
   RPC Signature V2 — нужен отдельный подписывающий метод в
   `alibaba_client.py`, не общий `_sign_request()`.
4. RegionId — обязательный параметр почти для всех операций (кроме RAM
   и BSS, которые глобальные) — если пользователь не укажет regionId
   явно, часть API вызовов будет падать с региональной ошибкой, а не
   тихо возвращать пустой список.

## 7. Release scope

Пользователь уже заявил максимум для категории — Ярус 1+2+3 без
повторного вопроса. Экспорт-контрольные ограничения на API-доступ (если
есть) будут обнаружены по факту при первом реальном connect (ошибка
аутентификации/доступа), не предполагаются заранее.
