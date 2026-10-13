#!/usr/bin/env python3
"""
Скрипт для тестирования всех поддерживаемых AI-провайдеров.
Проверяет доступность, скорость и способность возвращать валидный JSON.
"""
import os
import json
import time
import requests
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

TEST_PROMPT = """Верни СТРОГО валидный JSON без markdown и пояснений:
{"status": "success", "provider": "название_провайдера", "message": "тест прошел успешно"}"""

def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}")

def test_groq():
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        return "⚠️ Пропущено (нет GROQ_API_KEY в .env)"

    try:
        start = time.time()
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": TEST_PROMPT}], "temperature": 0.1},
            timeout=15
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        json.loads(content) # Проверка валидности JSON
        return f"✅ Успех за {time.time() - start:.2f}s | Модель: {model}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:100]}"

def test_openrouter():
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")
    if not api_key:
        return "⚠️ Пропущено (нет OPENROUTER_API_KEY в .env)"

    try:
        start = time.time()
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "VK Parser Test",
                "User-Agent": "curl/7.68.0" # Обход блокировок прокси
            },
            json={"model": model, "messages": [{"role": "user", "content": TEST_PROMPT}], "temperature": 0.1},
            timeout=20
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip().strip("`")
        if content.startswith("json"): content = content[4:].strip()
        json.loads(content)
        return f"✅ Успех за {time.time() - start:.2f}s | Модель: {model}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:100]}"

def test_qwen():
    api_key = os.getenv("QWEN_API_KEY")
    model = os.getenv("QWEN_MODEL", "qwen-plus")
    if not api_key:
        return "⚠️ Пропущено (нет QWEN_API_KEY в .env)"

    try:
        start = time.time()
        r = requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": TEST_PROMPT}], "temperature": 0.1, "response_format": {"type": "json_object"}},
            timeout=20
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        json.loads(content)
        return f"✅ Успех за {time.time() - start:.2f}s | Модель: {model}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:100]}"

def test_together():
    api_key = os.getenv("TOGETHER_API_KEY")
    model = os.getenv("TOGETHER_MODEL", "Qwen/Qwen2.5-72B-Instruct")
    if not api_key:
        return "⚠️ Пропущено (нет TOGETHER_API_KEY в .env)"

    try:
        start = time.time()
        r = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": TEST_PROMPT}], "temperature": 0.1, "response_format": {"type": "json_object"}},
            timeout=20
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        json.loads(content)
        return f"✅ Успех за {time.time() - start:.2f}s | Модель: {model}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:100]}"

def test_yandex():
    api_key = os.getenv("YANDEX_API_KEY")
    folder_id = os.getenv("YANDEX_FOLDER_ID")
    if not api_key or not folder_id:
        return "⚠️ Пропущено (нет YANDEX_API_KEY или YANDEX_FOLDER_ID в .env)"

    try:
        start = time.time()
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        payload = {
            "modelUri": f"gpt://{folder_id}/yandexgpt/latest",
            "completionOptions": {"stream": False, "temperature": 0.1, "maxTokens": "500"},
            "messages": [{"role": "user", "text": TEST_PROMPT}]
        }
        r = requests.post(url, headers={"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}, json=payload, timeout=15)
        r.raise_for_status()
        
        # Yandex возвращает JSON-строку внутри текстового поля
        result_text = r.json()["result"]["alternatives"][0]["message"]["text"]
        json.loads(result_text)
        return f"✅ Успех за {time.time() - start:.2f}s | Folder: {folder_id}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:100]}"

def test_ollama():
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    try:
        start = time.time()
        r = requests.post(
            f"{url}/api/chat",
            json={"model": model, "messages": [{"role": "user", "content": TEST_PROMPT}], "stream": False, "format": "json"},
            timeout=30
        )
        r.raise_for_status()
        content = r.json()["message"]["content"]
        json.loads(content)
        return f"✅ Успех за {time.time() - start:.2f}s | Модель: {model} (Локально)"
    except requests.exceptions.ConnectionError:
        return "❌ Ошибка: Не удается подключиться к localhost:11434. Запустите 'ollama serve'"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:100]}"

def main():
    print_header("🚀 ТЕСТИРОВАНИЕ AI ПРОВАЙДЕРОВ")
    print("Загрузка конфигурации из .env...\n")

    providers = [
        ("🦙 Ollama (Локальный)", test_ollama),
        ("⚡ Groq", test_groq),
        ("🌐 OpenRouter", test_openrouter),
        ("🔷 Qwen (DashScope)", test_qwen),
        ("🚀 Together AI", test_together),
        ("🇷🇺 YandexGPT", test_yandex),
    ]

    results = []
    for name, test_func in providers:
        print(f"Тестируем {name}...", end=" ")
        result = test_func()
        print(result)
        results.append((name, result))

    print_header("📊 ИТОГОВЫЙ ОТЧЕТ")
    success_count = sum(1 for _, res in results if "✅ Успех" in res)
    print(f"Успешно пройдено тестов: {success_count} из {len(providers)}\n")
    
    for name, res in results:
        status = "✅" if "✅" in res else ("⚠️" if "⚠️" in res else "❌")
        print(f"{status} {name}: {res}")

    print("\n💡 Рекомендация:")
    if success_count == 0:
        print("   Ни один провайдер не ответил. Проверьте интернет-соединение и файл .env.")
    elif "🇷🇺 YandexGPT" in [name for name, res in results if "✅" in res] or "🦙 Ollama" in [name for name, res in results if "✅" in res]:
        print("   Для российского сервера лучше всего использовать YandexGPT или Ollama (они работают стабильно без прокси).")
    else:
        print("   Используйте провайдеров с ✅ в основном файле .env (установите AI_PROVIDER=имя_провайдера).")

if __name__ == "__main__":
    main()