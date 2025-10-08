import json
import os
from anthropic import Anthropic
from typing import Dict, List, Any
import time

# Ініціалізація клієнта Anthropic
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def translate_category(category: str) -> str:
    """
    Перекладає назву категорії з польської на українську через Claude API
    """
    prompt = (
        f"Переклади назву категорії з польської на українську: {category}. "
        f"Переклади лише загальні слова. Якщо слово є брендом (назва виробника або моделі), не перекладай його. "
        f"Визнач самостійно, що є брендом. Поверни тільки переклад без лапок чи пояснень."
    )

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        translation = message.content[0].text.strip()
        print(f"'{category}' -> '{translation}'")
        return translation

    except Exception as e:
        print(f"Помилка перекладу '{category}': {e}")
        return category


def translate_category_structure(data: List[Dict[str, Any]], delay: float = 0.5) -> List[Dict[str, Any]]:
    """
    Рекурсивно перекладає всі назви категорій у структурі
    """
    translated_data = []

    for item in data:
        # Створюємо копію елемента
        translated_item = item.copy()

        # Перекладаємо назву категорії
        if "name" in translated_item:
            original_name = translated_item["name"]
            translated_item["name"] = translate_category(original_name)

            # Затримка між запитами, щоб не перевантажити API
            time.sleep(delay)

        # Рекурсивно обробляємо дочірні категорії
        if "children" in translated_item and translated_item["children"]:
            translated_item["children"] = translate_category_structure(
                translated_item["children"],
                delay
            )

        translated_data.append(translated_item)

    return translated_data


def process_file(input_filename: str, output_filename: str):
    """
    Обробляє один JSON файл: читає, перекладає та зберігає результат
    """
    print(f"\n{'='*60}")
    print(f"Обробка файлу: {input_filename}")
    print(f"{'='*60}\n")

    # Читаємо вхідний файл
    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ПОМИЛКА: Файл {input_filename} не знайдено!")
        return
    except json.JSONDecodeError as e:
        print(f"ПОМИЛКА: Некоректний JSON у файлі {input_filename}: {e}")
        return

    # Перекладаємо структуру
    translated_data = translate_category_structure(data)

    # Зберігаємо результат
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(translated_data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"Переклад завершено! Результат збережено у: {output_filename}")
    print(f"{'='*60}\n")


def main():
    """
    Головна функція для обробки всіх файлів
    """
    # Перевіряємо наявність API ключа
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ПОМИЛКА: Не встановлено змінну середовища ANTHROPIC_API_KEY")
        print("Встановіть її командою: set ANTHROPIC_API_KEY=your_api_key")
        return

    # Файли для обробки
    files_to_process = [
        ("2.json", "2_translated.json"),
        ("3.json", "3_translated.json"),
        ("4.json", "4_translated.json")
    ]

    # Обробляємо кожен файл
    for input_file, output_file in files_to_process:
        try:
            process_file(input_file, output_file)
        except KeyboardInterrupt:
            print("\n\nПереривання користувачем. Завершення роботи...")
            break
        except Exception as e:
            print(f"\nНесподівана помилка при обробці {input_file}: {e}")
            continue

    print("\n" + "="*60)
    print("Всі файли оброблено!")
    print("="*60)


if __name__ == "__main__":
    main()
