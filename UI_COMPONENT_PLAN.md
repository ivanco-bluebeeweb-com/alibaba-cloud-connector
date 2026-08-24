# Alibaba Cloud Connector — UI component plan

Источники: `Docs/session-notes/UI_INTERFACE_STANDARD.md`, `concepts/panels.md`.
Основано на `IDEAL_ONBOARDING.md` и `CONNECTOR_DISCOVERY.md` этого приложения.

## 0. Строится ДО panels.py

Как и для всех приложений категории (OCI, DigitalOcean), этот план
пишется на этапе preparation, а конкретный интерфейс строится сразу
вместе с кодом Яруса 1 — не после.

## 1. Компоненты

| Экран | Примитивы | Почему именно эти |
|---|---|---|
| Sidebar (left) | `ui.Stack`(direction="v", align="stretch") + список подключений + `ui.Divider` + `ui.Form`(connect) + `ui.Button`("App settings") | Без карточек по стандарту. `ui.Stack` НЕ принимает `full_width`/`full_height`/`label` — только `align`,`children`,`className`,`direction`,`gap`,`justify`,`sticky`,`wrap` (валидатор SDK проверяет это явно и отклоняет деплой). |
| Connect form | `ui.Form`(action="connect_alibaba_cloud") с полями через `_field(label, node)` — обёртка `ui.Stack`(direction="v", gap=1, align="stretch", children=[ui.Text(variant="caption"), node]) — AccessKey ID через `ui.Input`, AccessKey Secret через `ui.Password` (НЕ `ui.Input(input_type="password")` — этот параметр не существует, подтверждено деплой-валидатором на DigitalOcean Connector), Region ID (опционально) через `ui.Input` | `ui.Input` принимает только `param_name`/`placeholder`/`value`/`on_submit` — лейбл всегда отдельный `ui.Text(variant="caption")` над полем. Секретное поле — только `ui.Password`. |
| Cloud Overview (center, `center_overlay=True`) | `ui.Stack` с рядом `ui.Text` статистик (ECS running/stopped, OSS buckets, RDS instances, ACK clusters, баланс счёта) | Первый экран после подключения — сразу actionable сводка, без похода в консоль Alibaba Cloud. |
| App settings (center) | `ui.Stack` построчно на подключение — email/label, region по умолчанию, кнопка `ui.Button("Disconnect", variant="danger")` | Disconnect живёт ТОЛЬКО здесь, не в сайдбаре — по стандарту. |
| Connect help modal | `ui.Dialog` с шагами создания RAM AccessKey пары + рекомендацией read-only политики на старте | Инструкция здесь, НЕ дублируется в сайдбаре. |

## 2. Валидированные ограничения ui.* (подтверждено на OCI/DigitalOcean Connector's deploy_app)

- `ui.Stack`: `align`, `children`, `className`, `direction`, `gap`,
  `justify`, `sticky`, `wrap` — БЕЗ `full_width`/`full_height`.
- `ui.Button`: поддерживает `full_width` (в отличие от Stack).
- `ui.Input`: `on_submit`, `param_name`, `placeholder`, `value` — БЕЗ
  `label`, БЕЗ `input_type`.
- Секретные поля — отдельный компонент `ui.Password(param_name, placeholder)`.
- Лейблы полей — всегда отдельный `ui.Text(variant="caption")` прямо
  над полем ввода, никогда через несуществующий `label=` параметр.

## 3. User flow

1. Открыть приложение → sidebar показывает пустой список подключений +
   форму подключения (AccessKey ID + Secret + опц. Region).
2. Заполнить форму → `connect_alibaba_cloud` → лёгкая read-only
   проверка (`DescribeRegions`) → успех/явная ошибка.
3. После успеха → Cloud Overview автоматически (или по клику) —
   агрегированная сводка по ECS/OSS/RDS/ACK/балансу.
4. Сайдбар теперь показывает подключение (name/label) + кнопку "App
   settings" внизу.
5. В App settings — просмотр деталей подключения + Disconnect.
6. Через chat/tools — все Ярус 1-3 функции: list/get/start/stop/restart
   ECS-инстансов, list Spaces/RDS/ACK/CloudMonitor/Billing.
