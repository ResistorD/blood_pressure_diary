# blood_pressure_diary

Дневник давления

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Lab: Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Cookbook: Useful Flutter samples](https://docs.flutter.dev/cookbook)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

Строгая спецификация валидации (Business Logic)
1. Систолическое давление (SYS)
Диапазон: [50–250]

Первая цифра: Допустимы только 1, 2, 5, 6, 7, 8, 9.

Длина ввода:

Если начинается на 1 или 2 — ввод завершается строго после 3-й цифры.

Если начинается на 5, 6, 7, 8, 9 — ввод завершается строго после 2-й цифры.

Специфические правила:

Если первая цифра 2, то вторая допустима только в диапазоне [0–5].

2. Диастолическое давление (DIA)
Диапазон: [30–150]

Условия зависимости:

DIA < SYS (всегда меньше систолического).

SYS - DIA <= 110 (разница не более 110 единиц).

Первая цифра: Допустима 1 (если SYS > 100) или 3, 4, 5, 6, 7, 8, 9.

Длина ввода:

Если начинается на 1 — ввод завершается после 3-й цифры.

Если начинается на 3–9 — ввод завершается после 2-й цифры.

3. Пульс (PUL)
Диапазон: [30–250]

Первая цифра: Любая от 1 до 9.

Длина ввода:

Если начинается на 1 или 2 — ввод завершается после 3-й цифры.

Если начинается на 3–9 — ввод завершается после 2-й цифры.