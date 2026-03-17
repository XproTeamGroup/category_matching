# Category Expansion Plan

> Based on: `reference_structure.md` (current reference catalog) and `out_of_scope_grouped.md` (supplier gaps).
> Goal: decide which out-of-scope clusters to add to the reference, where they belong, and which to exclude.

---

## Decision Framework

Each out-of-scope cluster falls into one of three buckets:

| Status | Meaning |
|--------|---------|
| **ADD** | Genuinely missing from reference; fits the store's weapons/tactical/outdoor domain |
| **EXTEND** | Partially covered — needs new subcategories inside an existing branch |
| **EXCLUDE** | Out of domain for this catalog (consumer electronics, toys, fitness, etc.) |

---

## Cluster-by-Cluster Decisions

---

### Cluster 1 — Дрони та безпілотники

**Decision: ADD — New top-level category**

Drones are now deeply embedded in the tactical/military space (FPV strike drones, recon, thermal imaging platforms). DJI Mavic, AUTEL, Matrice 4, FPV, and thermal-equipped models are all combat-relevant products.

**Proposed new top-level category: `Дрони та БпЛА`**

```
Дрони та БпЛА
├── FPV дрони
├── Розвідувальні дрони
│   ├── DJI Mavic серія
│   ├── AUTEL
│   ├── Matrice 4
│   └── З тепловізором
├── Антени та підсилювачі сигналу
└── Аксесуари та комплектуючі
```

---

### Cluster 2 — Зв'язок та радіообладнання

**Decision: ADD — New top-level category**

Tactical communications (walkie-talkies, repeaters, Starlink vehicle kits, Wi-Fi bridges) are core military/tactical products. None exist in the current reference.

**Proposed new top-level category: `Зв'язок`**

```
Зв'язок
├── Рації та радіостанції
├── Ретранслятори
├── Wi-Fi мости та маршрутизатори
└── Starlink
    └── Старлінк на авто
```

---

### Cluster 3 — Оптика нічного бачення

**Decision: EXTEND — Expand existing `Оптика > Приціли та прилади нічного бачення (ПНБ)`**

The reference already has the category `Оптика > Приціли та прилади нічного бачення (ПНБ)` but only has `Аксесуари` underneath it. The brand-level subcategories and device-type splits are missing entirely.

**Proposed extension of `Оптика > Приціли та прилади нічного бачення (ПНБ)`:**

```
Оптика > Приціли та прилади нічного бачення (ПНБ)
├── Приціли нічного бачення          ← NEW
│   ├── Archer
│   ├── HikMicro
│   ├── PARD
│   ├── Rix
│   ├── Dedal
│   ├── Sytong
│   ├── ARMASIGHT
│   └── Dipol
├── Окуляри нічного бачення          ← NEW
│   ├── AGM
│   ├── ATN
│   ├── Pulsar
│   ├── Yukon
│   ├── Konus
│   ├── Беломо
│   └── Nortis
├── Тепловізори                       ← NEW
└── Аксесуари                        ← already exists
```

> Note: Brand-level subcategories may be optional depending on catalog philosophy.
> At minimum, the three device-type nodes (Приціли НБ / Окуляри НБ / Тепловізори) should be added.

---

### Cluster 4 — Мікроскопи та астрономія

**Decision: EXCLUDE (partially)**

- **Мікроскопи (Біологічні, Стерео, Дитячі)**: Out of domain. These are laboratory/educational products with no tactical relevance.
- **Астрономія > Цифрові камери для телескопів**: Out of domain.
- **Мікроскопи Кишенькові / Цифрові**: Borderline — could theoretically fit in a "field optics" context, but too niche. Recommend EXCLUDE.

**Action: No additions to reference for this cluster.**

---

### Cluster 5 — Зарядні станції та живлення

**Decision: ADD — New subcategory under existing or new parent**

Portable power (charging stations, power banks, batteries) is highly relevant for field/military use. Currently no power-supply category exists in the reference.

**Option A** — Add under existing `Спорядження`:
```
Спорядження
└── Живлення та зарядні пристрої    ← NEW
    ├── Зарядні станції
    └── Повербанки та акумулятори
```

**Option B** — Create new top-level `Живлення` (if catalog will grow significantly in this area).

**Recommendation: Option A** (extend Спорядження) unless drone/comms accessories also need power subcategories.

---

### Cluster 6 — Релоадинг

**Decision: ADD — New top-level category**

Reloading equipment (hand-loading ammunition components, presses, dies, powder measures, bullet casting) is a legitimate and substantial niche within a firearms store. It does not fit naturally under any existing reference branch.

**Proposed new top-level category: `Релоадинг`**

```
Релоадинг
├── Гладкоствольна зброя
│   ├── Станки та матриці
│   └── Запчастини
├── Нарізна зброя
│   ├── Преси
│   ├── Матриці та шелхолдери
│   ├── Калібратори
│   ├── Капсулятори та де-капсулятори
│   ├── Підготовка гільз
│   └── Воронки та мастила
├── Дозатори пороху
│   ├── Механічні
│   ├── Електронні
│   └── Інші
├── Вимірювальний інструмент
│   ├── Штангенциркулі
│   ├── Компаратори
│   ├── Хронографи
│   └── Спец. інструмент
├── Лиття куль
│   ├── Тиглі
│   ├── Пулелейки
│   ├── Сайзери
│   ├── Форми картечі
│   └── Покриття та інше
└── Ваги для пороху
```

---

### Cluster 7 — Засоби самооборони та макети

**Decision: MIXED**

- **Засоби для самооборони** (pepper spray, stun guns, etc.): CONSIDER ADD. Could sit under existing `Зброя` or as a new subcategory. If the store carries these, add `Зброя > Засоби самооборони`.
- **Макети масо-габаритні (ММГ)**: EXTEND — Add under `Зброя > Вогнепальна зброя` or as `Зброя > Макети та ММГ`. These are deactivated weapons used for training/display.
- **Б/В ММГ та СХП (used/deactivated)**: EXCLUDE from matching — "б/у" (used goods) is a condition tag, not a category. Should not be added as a structural category.

**Proposed additions:**
```
Зброя
├── Засоби самооборони               ← NEW (if in scope)
└── Макети та ММГ                    ← NEW
```

---

### Cluster 8 — Туризм та відпочинок

**Decision: PARTIAL EXCLUDE / PARTIAL ADD**

- **Намети / Тенти, Туристичні меблі, Мангали, Холодильники та термоси**: These are outdoor/camping goods. The store is tactical/weapons-focused. If an "outdoor" section is in scope, add under a new `Туризм та відпочинок` top-level. Otherwise EXCLUDE.
- **Спортивні товари** (generic): EXCLUDE — too vague and off-domain.
- **Генератори**: CONSIDER ADD — field generators are tactically relevant and could go under `Спорядження > Живлення та зарядні пристрої` or standalone.

**Recommendation:** Add `Генератори` under `Спорядження > Живлення та зарядні пристрої`. Exclude the rest of this cluster unless the catalog explicitly expands into camping/outdoor retail.

---

### Cluster 9 — Вимірювальне та метео обладнання

**Decision: PARTIAL ADD**

- **Хронографи**: Already proposed under `Релоадинг > Вимірювальний інструмент`. Also relevant standalone. Consider adding to `Аксесуари` or `Чистка та догляд`.
- **Метеостанції**: Tactically relevant (for long-range shooting — wind, temp, humidity). ADD under `Оптика > Аксесуари та комплектуючі` or standalone `Аксесуари > Балістичні калькулятори та метео`.
- **Штативи**: ADD — universal shooting accessory. Fits under `Аксесуари > Упори для стрільби` or as a new node.

**Proposed additions:**
```
Аксесуари
├── Хронографи                       ← NEW
└── Метеостанції                     ← NEW
```
or, more elegantly, extend `Тюнінг > Ключі та інструменти` or create a dedicated `Вимірювання та балістика` subcategory under `Аксесуари`.

---

### Cluster 10 — Годинники, навігація та спортивна електроніка

**Decision: PARTIAL ADD / PARTIAL EXCLUDE**

- **Спортивний годинник, Велокомп'ютери, Смарт-ваги, Кардіотренажери, Велосипедні машини**: EXCLUDE — consumer fitness electronics, out of domain.
- **Навігатори (GPS)**: ADD — tactically relevant. Fits under a new `Навігація` node or `Спорядження > Навігація`.
- **Морське обладнання**: EXCLUDE — niche off-domain.
- **Камери (action/body cameras)**: BORDERLINE — tactical body cameras are relevant. Could add `Спорядження > Тактичні камери` if supplier carries military-oriented models.
- **Трекер для собак**: BORDERLINE — relevant for military/working dogs. Low priority.
- **Зарядні пристрої / Кабелі**: EXTEND — add under proposed `Спорядження > Живлення та зарядні пристрої`.

**Proposed additions:**
```
Спорядження
└── Навігація                        ← NEW
    └── GPS-навігатори
```

---

### Cluster 11 — Іграшки

**Decision: EXCLUDE**

Toys are completely out of domain for a weapons/tactical store. Do not add.

---

### Cluster 12 — Різне (Релоадинг побутове)

**Decision: PARTIAL EXCLUDE**

- **Динамометричні викрутки**: ADD — gunsmithing tool. Fits under `Тюнінг > Ключі та інструменти` or `Чистка та догляд`.
- **Підставки для гільз**: ADD — fits under `Релоадинг` (new category) or `Чистка та догляд`.
- **Товари б/у / Несортовані**: EXCLUDE — operational/workflow tags, not catalog categories.

---

## Summary Table

| Cluster | Decision | Where to Add |
|---------|----------|--------------|
| Дрони та БпЛА | ADD (new top-level) | `Дрони та БпЛА` |
| Зв'язок та радіо | ADD (new top-level) | `Зв'язок` |
| Оптика нічного бачення | EXTEND | `Оптика > Приціли та прилади нічного бачення (ПНБ)` |
| Мікроскопи та астрономія | EXCLUDE | — |
| Зарядні станції / живлення | ADD (new sub) | `Спорядження > Живлення та зарядні пристрої` |
| Релоадинг | ADD (new top-level) | `Релоадинг` |
| Засоби самооборони | PARTIAL ADD | `Зброя > Засоби самооборони` + `Зброя > Макети та ММГ` |
| Туризм та відпочинок | PARTIAL EXCLUDE | `Спорядження > Живлення` (generators only) |
| Метео та вимірювання | PARTIAL ADD | `Аксесуари > Хронографи`, `Аксесуари > Метеостанції` |
| Годинники / навігація / фітнес | PARTIAL ADD | `Спорядження > Навігація`; решта EXCLUDE |
| Іграшки | EXCLUDE | — |
| Різне релоадинг | PARTIAL ADD | `Тюнінг > Ключі та інструменти` (динамометричні), `Релоадинг` (підставки для гільз) |

---

## Proposed New Top-Level Categories (3)

| # | New Top-Level | Rationale |
|---|---------------|-----------|
| 1 | **Дрони та БпЛА** | Tactical drones are a major product category in the modern military market |
| 2 | **Зв'язок** | Tactical comms (radios, Starlink, repeaters) are a distinct product domain |
| 3 | **Релоадинг** | Hand-loading ammunition is a well-established firearms niche with unique tooling |

---

## Proposed Extensions to Existing Categories

| Existing Category | New Subcategories |
|-------------------|-------------------|
| `Оптика > Приціли та прилади нічного бачення (ПНБ)` | Приціли НБ, Окуляри НБ, Тепловізори |
| `Спорядження` | Живлення та зарядні пристрої, Навігація |
| `Зброя` | Засоби самооборони, Макети та ММГ |
| `Аксесуари` | Хронографи, Метеостанції |
| `Тюнінг > Ключі та інструменти` | (absorb динамометричні викрутки) |

---

## Firmly Excluded (Do Not Add)

- Мікроскопи (біологічні, дитячі, стерео)
- Астрономія > Цифрові камери для телескопів
- Спортивні товари (generic)
- Туристичні меблі, Мангали, Холодильники та термоси
- Велокомп'ютери, Кардіотренажери, Велосипедні машини
- Морське обладнання
- Смарт-ваги (consumer)
- Іграшки
- Б/У товари / Несортовані (workflow tags, not categories)
- Трекер для собак (low priority, borderline)
