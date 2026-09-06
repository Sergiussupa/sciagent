# Demo: 10-paper persistent research session

**Date:** 2026-09-06
**Model:** qwen3:14b
**Source:** arXiv
**Query:** `neuromorphic vision event cameras`

This document captures a real intermediate SciAgent prototype run.

The generated scientific answers are not yet evidence-grade.

## 1. Start a multi-paper ResearchRun

```bash
SCIAGENT_MODEL=qwen3:14b \
python scripts/run_research_run.py \
  "neuromorphic vision event cameras" \
  --max-papers 10 \
  --days 365 \
  --run-id event_vision_10_v01
```

Observed result:

```text
RESEARCH RUN COMPLETE

completed: 10
failed: 0
```

Workspace:

```text
state/research_runs/event_vision_10_v01/workspace.sqlite3
```

Manifest:

```text
state/research_runs/event_vision_10_v01/papers.json
```

Report:

```text
state/research_runs/event_vision_10_v01/report.md
```

## 2. Papers processed

The run processed 10 real arXiv papers:

- Residual Kalman Dynamics for Event-Based UAV Forecasting
- ANTShapes Benchmarking Datasets for Event-Based Neuromorphic Object Classification
- EsaacSim: A Multimodal Event Camera Add-on for NVIDIA Isaac Sim
- Cooking beyond Frames: A Stereo Event Camera Dataset in the Kitchen
- PLS-Calib: A Partial Least Squares Framework for Event Camera and Odometry Calibration under Ground Motion Constraints
- Event-Based Upper-Body Humanoid Teleoperation Under Challenging Illumination
- Neuromorphic Object Detection: An In-Depth Study and Future Directions
- DeLux: Cross-Modal Local Artifact Restoration in Video Using Neuromorphic Data
- Low-Cost Neuromorphic Fall Detection Using Synthetic Event Data and Hybrid SNNs
- FPGA-Accelerated Neuromorphic Vision System for Real-Time Orbital Object Detection

## 3. Network resume example

One PDF download was interrupted by a timeout.

Observed behavior:

```text
download interrupted: Read timed out
retrying in 3.0s...

download: resume from 1.2 MB

...

download complete: 19.3 MB
```

Processing then continued normally.

## 4. ResearchWorkspace contents

Observed knowledge counts:

```text
baseline                       92
claim                         400
claim_consolidation_group      81
condition                     121
dataset                       146
method                        214
metric                        165
model                         140
paper_claim                   107
research_question             115
system                        103
task                           99
```

The important architectural property is that this knowledge remains persistent on disk.

It does not need to fit inside one LLM context.

## 5. One-shot question

Command:

```bash
SCIAGENT_MODEL=qwen3:14b \
python -m sciagent ask \
  --run-id event_vision_10_v01 \
  --question "Какие главные технологии используются в этих десяти статьях?"
```

The answer identified technologies including:

- Dynamic Vision Sensors
- Address-Event Representation
- Spiking Neural Networks
- hybrid SNN-CNN models
- neuromorphic computing platforms
- FPGA acceleration
- stereo event cameras
- Recurrent Vision Transformers
- synthetic event data
- event-camera calibration methods

Retrieved knowledge objects were referenced using internal markers such as:

```text
[K2]
[K12]
[K20]
```

## 6. Interactive session

Command:

```bash
SCIAGENT_MODEL=qwen3:14b \
python -m sciagent ask \
  --run-id event_vision_10_v01
```

Observed interface:

```text
SciAgent research session: event_vision_10_v01
Papers: 10

Ask questions about the existing ResearchWorkspace.
Commands: :status  :papers  :help  :quit

sciagent>
```

Example dialogue:

```text
sciagent> Какие главные технологии используются?

sciagent> Почему event cameras отличаются от обычных камер?

sciagent> Какие проблемы чаще всего возникают?

sciagent> Какие из этих проблем связаны именно с низким освещением?
```

The last question depends on the previous dialogue.

SciAgent reused the same ResearchWorkspace and recent dialogue instead of rebuilding the research corpus.


## 6.1 Observed interactive transcript

Below is an actual transcript produced by the prototype using `qwen3:14b`.

### Question 1

```text
sciagent> Какие главные технологии используются?
```

SciAgent answered:

> В этих статьях используются следующие главные технологии:
>
> 1. **Address-Event Representation (AER)** — формат, используемый для кодирования асинхронных событий с динамических визуальных датчиков, представляющий каждое событие как кортеж (x, y, t, p) [K11].
>
> 2. **Спайки нейронные сети (SNNs)** — тип нейронной сети, которая обрабатывает информацию в виде импульсов, что делает её подходящей для низкопотребляющих нейроморфных вычислений [K25].
>
> 3. **Гибридные модели SNN-CNN** — модели, объединяющие спайки нейронные сети с CNN для обнаружения падений с использованием симулированных данных с нейроморфных камер [K14].
>
> 4. **Нейроморфные вычислительные платформы** — специализированные аппаратные платформы для выполнения SNN и обработки событий [K17].
>
> 5. **FPGA-ускоренные нейроморфные системы визуального восприятия** — системы для низкой задержки и обработки данных в реальном времени [K19].
>
> 6. **Стерео-камеры с событиями** — используются для сбора event-based данных в реальных условиях [K3].
>
> 7. **Recurrent Vision Transformers (RVT)** — модели обнаружения объектов на основе событий [K12].
>
> 8. **Синтетические event-based данные** — используются для моделирования реальных DVS-сенсоров [K4].
>
> 9. **Методы калибровки event cameras**, включая PLS-Calib [K29].
>
> 10. **Event-based object detection models**, включая EvRT-DETR [K24].

### Question 2

```text
sciagent> Почему event cameras отличаются от обычных камер?
```

SciAgent answered:

> Event cameras отличаются от обычных камер по нескольким ключевым аспектам:
>
> 1. **Асинхронная передача данных** — event cameras передают изменения сцены как события, вместо последовательности полных кадров [K19].
>
> 2. **Address-Event Representation (AER)** — каждое событие представляется как `(x, y, t, p)`, где `p` описывает знак изменения интенсивности [K16].
>
> 3. **Высокая чувствительность к движению и контрасту** — особенно полезна в динамичных сценах и при быстром движении [K5].
>
> 4. **Низкое энергопотребление** — передаются только изменения, а не полные изображения [K20].
>
> 5. **Специализированное аппаратное ускорение** — например FPGA для низкой задержки [K22].
>
> 6. Для обучения и тестирования также могут использоваться **синтетические event-based данные** [K8].

### Question 3

```text
sciagent> Какие проблемы чаще всего возникают?
```

SciAgent answered:

> На основе представленных знаний были выделены следующие проблемы:
>
> 1. Ограничения при обработке **статических текстур и статических сцен** [K4].
>
> 2. Недостаток богатых текстурных деталей по сравнению с RGB [K4].
>
> 3. **Сложности калибровки** event cameras [K1][K12].
>
> 4. Возможные проблемы с **обработкой высокой частоты событий в реальном времени** [K2].
>
> 5. Ограниченная реалистичность некоторых синтетических наборов данных [K8].
>
> 6. Проблемы восстановления артефактов в некоторых конфигурациях DeLux [K29].
>
> 7. Снижение точности или полноты обнаружения при отсутствии части event-based информации [K29].

### Question 4 — contextual follow-up

```text
sciagent> Какие из этих проблем связаны именно с низким освещением?
```

SciAgent answered:

> На основе представленных знаний система связала с низким освещением:
>
> 1. трудности обработки данных и калибровки [K1][K3][K7];
>
> 2. недостаток богатых текстурных деталей [K20];
>
> 3. проблемы восстановления артефактов [K26];
>
> 4. ограничения обработки статических текстур [K4][K20].

This last answer is especially useful as a prototype diagnostic.

The system successfully understood the conversational reference **"этих проблем"**, but some low-light relationships may have been inferred more strongly than the retrieved evidence directly supports.

This is a concrete example of both:

- working conversational continuity;
- the current need for stronger evidence verification.


## 7. Resume behavior

Research stages are checkpointed.

Re-running an already processed ResearchRun can produce:

```text
research design...
  design: already_completed

claims...
  claims: already_completed

consolidate...
  paper claims: ...
```

Downloaded PDFs are also reused from cache.

The ResearchRun therefore behaves as persistent research state rather than a single disposable prompt.

## 8. Current scientific-quality warning

The prototype can already produce useful cross-paper answers, but the answers are not yet evidence-grade.

A follow-up answer may occasionally strengthen a plausible relationship beyond what the retrieved evidence directly proves.

This demo therefore demonstrates that the architecture works end-to-end, not that scientific verification is complete.

## 9. Why this milestone matters

```text
10 papers
    |
    v
persistent extracted knowledge
    |
    v
bounded retrieval
    |
    v
multiple conversational questions
```

This is the small-scale version of the intended future workflow:

```text
100+ papers
    |
    v
ResearchWorkspace
    |
    v
incremental extraction and consolidation
    |
    v
persistent research session
    |
    v
cross-paper scientific synthesis
```
