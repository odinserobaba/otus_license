# DEPLOY CHECKLIST (for Coursework Defense)


## 0) Что нужно заранее

- Linux VM в РФ (рекомендуется Yandex Cloud, Ubuntu 22.04/24.04).
- Публичный IP сервера.
- Домен (опционально, но желательно для HTTPS).
- Ключ `YANDEX_CLOUD_API_KEY`.

## 1) Подготовка сервера

```bash
git clone <repo_url> /opt/normatives
cd /opt/normatives
chmod +x release/deploy/provision_ubuntu.sh
sudo ./release/deploy/provision_ubuntu.sh
```

Что показать:
- скрин с успешным завершением bootstrap (`Bootstrap completed`).

## 2) Настройка окружения

```bash
cd /opt/normatives
cp release/.env.final.example .env.final
```

Заполните в `.env.final` минимум:
- `YANDEX_CLOUD_API_KEY`
- `YANDEX_CLOUD_FOLDER`

Для reverse proxy:
- `WEB_SERVER_NAME=127.0.0.1`
- `WEB_SERVER_PORT=7860`

Что показать:
- скрин фрагмента `.env.final` без полного секрета (например, `AQVN...D0e`).

## 3) Запуск как systemd service

```bash
cd /opt/normatives
sudo cp release/deploy/systemd/normatives-rag.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now normatives-rag
sudo systemctl status normatives-rag --no-pager
```

Что показать:
- `Active: active (running)` в `systemctl status`.

## 4) Настройка nginx

```bash
sudo cp release/deploy/nginx/normatives-rag.conf /etc/nginx/sites-available/normatives-rag
sudo ln -sf /etc/nginx/sites-available/normatives-rag /etc/nginx/sites-enabled/normatives-rag
sudo nginx -t
sudo systemctl reload nginx
```

Проверка:

```bash
curl -I http://127.0.0.1:7860
curl -I http://<PUBLIC_IP>
```

Что показать:
- `HTTP/1.1 200 OK` (или редирект 301/302, если настроен HTTPS).

## 5) Демонстрация веб-интерфейса

Откройте:
- `http://<PUBLIC_IP>` (или домен)

Проверьте 2-3 запроса:
- отказ в лицензии (ст. 19 171-ФЗ),
- подача через ЕПГУ (приказ №199),
- исключения выездной оценки (пункт 29, №1720).

Что показать:
- скрин UI с вопросом и ответом;
- блок `### Источники` с нормальными ссылками.

## 6) Артефакты качества (для отчёта)

Финальные файлы:
- `processed/iter4_full_20_eval_keyretry_report.md`
- `processed/iter4_full_20_eval_keyretry_qa.md`
- `processed/iter4_full_extra10_eval_keyretry_report.md`
- `processed/iter4_full_extra10_eval_keyretry_qa.md`

Что показать:
- итоговые строки `ok/partial/bad`;
- примеры QA по 1-2 вопросам.

## 7) Что сказать на защите (кратко)

- Используется RAG-пайплайн с retrieval + post-processing для юридической точности.
- Развёртывание выполнено на Linux VM в РФ через `systemd + nginx`.
- Внешний LLM вызывается по API (Yandex Cloud).
- Есть fallback-поведение и контроль качества источников.

## 8) Быстрый plan B при сбое

Если сервис не поднялся:

```bash
sudo journalctl -u normatives-rag -n 200 --no-pager
sudo systemctl restart normatives-rag
```

Если nginx не проксирует:

```bash
sudo nginx -t
sudo systemctl restart nginx
curl -I http://127.0.0.1:7860
```

## 9) Перед сдачей

Очистка временных файлов:

```bash
cd /opt/normatives
chmod +x release/deploy/cleanup_coursework_artifacts.sh
./release/deploy/cleanup_coursework_artifacts.sh
```

Проверить, что остались только финальные QA-артефакты `iter4_full_*_keyretry*`.
