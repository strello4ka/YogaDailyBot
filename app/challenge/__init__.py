"""Челлендж: поток по дате, сводки, расписание, старт/финал.

Структура папок:

summary/          — утренние сводки в группе
  messages.py     — тексты сводок
  job.py          — автоотправка 10:10
  commands.py     — /challenge_summary_preview, /challenge_summary_reset

week_schedule/    — воскресное расписание в группе
  messages.py     — текст «расписание на неделю»
  job.py          — автоотправка вс 20:00
  commands.py     — /challenge_schedule_preview

flow/             — старт и завершение в личке
  start_flow.py   — приветствие, выбор и сохранение времени
  flow_add_command.py — основная запись /flow_add
  exit_flow.py    — общее завершение (текст + pending + режим)
  exit_job.py     — автозавершение на день 29
  hand_commands.py — запасные /challenge и /challenge_off

cohort.py         — календарь потока и константы (28 дней, 10:10, 20:00, …)
jobs.py           — регистрация фоновых задач
"""
