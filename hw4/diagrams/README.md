# Диаграммы RFC

В сдаваемом наборе **6 диаграмм**: 2 C4 Container и 4 sequence. Исходники — PlantUML (`.puml`), результаты — SVG для масштабирования и PNG для просмотра. C4 использует встроенную библиотеку `<C4/C4_Container>`; это приложения/хранилища, а не deployment Docker.

| Файл                                                                                       | Назначение                                                 |
| ------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| [a-container.svg](a-container.svg) / [PNG](a-container.png) / [исходник](a-container.puml) | C4 Container варианта A: PostgreSQL + Kafka + свой автомат |
| [a-normal.svg](a-normal.svg) / [PNG](a-normal.png) / [исходник](a-normal.puml)             | Штатная доставка A, push и подтверждение приложения        |
| [a-failover.svg](a-failover.svg) / [PNG](a-failover.png) / [исходник](a-failover.puml)     | Failover A, SMS и поздний push receipt                     |
| [b-container.svg](b-container.svg) / [PNG](b-container.png) / [исходник](b-container.puml) | C4 Container варианта B: Temporal workflow и ledger        |
| [b-normal.svg](b-normal.svg) / [PNG](b-normal.png) / [исходник](b-normal.puml)             | Штатный workflow B и надёжная передача receipt в Signal    |
| [b-failover.svg](b-failover.svg) / [PNG](b-failover.png) / [исходник](b-failover.puml)     | Durable timer, replay и резервная SMS Activity             |

## Как читать C4

Верхний ряд — приём, журнал и приём подтверждений. Ниже — передача/выполнение задач; внешние каналы расположены справа, настройки и вспомогательные контейнеры — отдельно снизу.

Основания оформления: [C4 notation](https://c4model.com/diagrams/notation), [C4 checklist](https://c4model.com/diagrams/checklist), [C4-PlantUML layout](https://github.com/plantuml-stdlib/C4-PlantUML/blob/master/LayoutOptions.md).

## Воспроизведение

Из корня репозитория с установленной Java и PlantUML JAR:

```sh
java -Djava.awt.headless=true -jar /path/to/plantuml.jar -charset UTF-8 -tsvg 'hw4/diagrams/*.puml'
java -Djava.awt.headless=true -jar /path/to/plantuml.jar -charset UTF-8 -tpng 'hw4/diagrams/*.puml'
```

Путь к JAR заменить реальным.
