# StoryBeat 触发系统语法参考

StoryBeat 是引擎区别于"纯 AI 生成"的核心——作者在特定游戏状态下插入手写内容，确保关键剧情节点 100% 可控。

## 基本结构

```yaml
beats:
  - id: beat_unique_id       # 唯一标识符（必填）
    kind: dialogue            # 叙事类型：dialogue / event / description / all（默认 all）
    title: 人类可读标题        # 可选，用于调试
    priority: 80              # 优先级，越大越优先（默认 0）
    once: true                # 是否仅触发一次（默认 true）
    trigger: { ... }          # 触发条件（必填）
    # 以下为手写输出
    text: "手写文案内容"
    mood: eerie               # description 专用
    mood_change: -1           # dialogue 专用，情绪变化值 (-10 ~ 10)
    unlock_hint: key_found    # dialogue 专用，解锁线索 ID
    event_title: 事件标题      # event 专用
    event_choices: [... ]     # event 专用
    event_consequences: { ... } # event 专用
    unlocks: [flag_ids]        # 触发后设置的状态标记
```

### kind 字段详解

`kind` 控制 beat 只对特定叙事类型生效：

| kind 值 | 触发时机 |
|---------|---------|
| `dialogue` | 仅 `tell(kind="dialogue")` 时匹配 |
| `event` | 仅 `tell(kind="event")` 时匹配 |
| `description` | 仅 `tell(kind="description")` 时匹配 |
| `all`（默认） | 任意 `kind` 都匹配 |

```yaml
# 只在生成对话时触发——避免 event/description 误吃
- id: npc_special_dialogue
  kind: dialogue
  trigger:
    world.area: old_dock
    _npc_id: fishmonger_li
  text: "孩子，你知道这片海以前叫什么吗？"
```

不设 `kind`（或设 `all`）时，beat 对三种叙事类型都参与匹配。适合纯环境描述类的锚点。

## 触发条件 (trigger)

### 字段路径

触发条件通过点号路径访问 GameState 的任意字段：

| 路径 | 访问的值 |
|------|---------|
| `world.area` | `state.world.area` |
| `world.time` | `state.world.time` |
| `world.weather` | `state.world.weather` |
| `world.chapter` | `state.world.chapter` |
| `player.attributes.san` | `state.player.attributes["san"]` |
| `player.attributes.str` | `state.player.attributes["str"]` |
| `player.flags.met_li` | `state.player.flags["met_li"]` |
| `player.inventory` | `state.player.inventory` (列表) |
| `player.recent_actions` | `state.player.recent_actions` (列表) |

### 精确匹配

```yaml
trigger:
  world.area: grandma_house     # 值完全相等时触发
  world.time: night
```

当 `area == "grandma_house"` **且** `time == "night"` 时触发。

### 比较运算符

```yaml
trigger:
  player.attributes.san: "<=80"    # san ≤ 80
  player.attributes.str: ">5"       # str > 5
```

支持的运算符：

| 运算符 | 含义 | 示例 |
|--------|------|------|
| `>=` | 大于等于 | `">=50"` |
| `<=` | 小于等于 | `"<=80"` |
| `>` | 大于 | `">10"` |
| `<` | 小于 | `"<30"` |
| `==` | 等于 | `"==100"` |

注意：运算符必须用引号包裹，否则 YAML 会把 `<=80` 解析为非字符串。

### 正则匹配

```yaml
trigger:
  world.area: "/dock|码头/"       # area 包含 "dock" 或 "码头"
```

使用 `/pattern/` 包裹，支持 Python 正则语法。正则匹配使用 `re.search`（部分匹配）。

### $or 条件组

```yaml
trigger:
  $or:
    - world.area: grandma_house
      world.time: night
    - world.area: old_dock
      world.time: dusk
```

任一子条件组完全满足即触发。每个子条件组内部是 AND 关系。

### $not 取反

```yaml
trigger:
  $not:
    $or:
      - world.area: market
      - world.area: grandma_house
  player.attributes.san: "<=60"
```

`$not` 内的条件**不满足**时才触发。上例：area 不是 market 也不是 grandma_house，且 san ≤ 60。

### 列表包含

```yaml
trigger:
  player.inventory: "旧相机"       # inventory 列表中包含 "旧相机"
```

用于 `player.inventory` (list[str]) 和 `player.recent_actions` (list[str])。

### 组合示例

```yaml
# 最复杂的组合：$or + 正则 + 比较
trigger:
  $or:
    - world.area: "/dock|码头/"
      world.time: night
    - world.area: "/cemetery|墓地|坟墓/"
      world.time: dusk
  player.attributes.san: "<=80"
  player.flags.chapter1_start: true
```

## 虚拟字段

虚拟字段从 GameState 动态派生，不直接存储在 state 中：

| 虚拟字段 | 派生逻辑 | 类型 |
|----------|---------|------|
| `_inventory_count` | `len(player.inventory)` | int |
| `_history_count` | `len(state.history)` | int |
| `_npc_count` | `len(state.npcs)` | int |
| `_npc_id` | 当前 `npc_id` 参数 | str |

```yaml
trigger:
  _inventory_count: ">=3"         # 背包有 3 件以上物品
  _npc_id: fishmonger_li          # 当前交互 NPC 是 fishmonger_li
```

`_npc_id` 只在 `tell()` 传了 `npc_id` 时才有值——通常配合 `kind: dialogue` 使用，避免在 event/description 场景下误命中。

游戏特定的计数（照片数、好感度、声望等）请用 `player.attributes.<key>` 在游戏侧维护，触发器写 `player.attributes.photos: ">=12"` 即可。

## 优先级与 once 语义

### priority

多个 beat 同时满足触发条件时，**priority 最大者胜出**。

```yaml
beats:
  - id: generic_greeting
    priority: 10
    trigger:
      world.area: old_dock
    text: "渔港的空气带着咸味。"

  - id: specific_event
    priority: 80
    trigger:
      world.area: old_dock
      player.flags.met_li: true
    text: "鱼贩老李对你点了点头，像是认出了你。"
```

两者都在 `old_dock` 触发，但 `specific_event` 的 priority 更高（且条件更严格），会优先触发。

### once

- `once: true`（默认）：触发后标记为 `fired`，之后不再触发。适合关键剧情节点。
- `once: false`：每次条件满足都会触发。适合环境描述、常数化反馈。

```yaml
# 每次下雨都会触发的环境描述
- id: weather_rain
  once: false
  priority: 5
  trigger:
    world.weather: rain
  text: "雨水打在石板路上，发出细碎的响声。"

# 每次进入市场都能看到的基础描述（低优先级，可被更高优先级 beat 覆盖）
- id: market_ambient
  once: false
  priority: 2
  kind: description
  trigger:
    world.area: market
  text: "市场里人来人往，摊贩的吆喝声此起彼伏。"
```

注意：`once: false` 的 beat 不能被更高优先级的 beat "覆盖"——beat 匹配只取 priority 最高的那个。如果你想让市场描述作为"兜底"（只在没有更具体的 beat 命中时触发），给它设低 priority 值。

## 手写输出

### Dialogue 对话

```yaml
- id: npc_recognize
  kind: dialogue
  trigger:
    world.area: old_dock
    _npc_id: fishmonger_li
  text: "你奶奶……欠我一碗汤。二十年了。"
  mood_change: -1
  unlock_hint: grandma_recipe_soup
```

### Event 事件

```yaml
- id: night_encounter
  kind: event
  trigger:
    $or:
      - world.area: "/dock|码头/"
        world.time: night
  event_title: 暗处有东西在看你
  text: "水面下有什么巨大的轮廓缓缓滑过……"
  event_choices:
    - 举起相机
    - 慢慢后退
    - 扔一块石头
  event_consequences:
    举起相机: 取景框里的画面让你的手止不住地颤抖——那不是鱼。
    慢慢后退: 它没有追上来，但你清楚地听到了水花溅起的声音。
    扔一块石头: 水面猛地炸开。那东西的速度远超你的预期。
```

### Description 场景描述

```yaml
- id: unsafe_path
  kind: description
  trigger:
    $not:
      $or:
        - world.area: market
        - world.area: grandma_house
  text: "你拐进了一条游客不会踏足的小路。石板湿滑，空气里弥漫着说不清的腥味。"
  mood: eerie
```

## 状态标记 (unlocks)

```yaml
- id: prologue_arrival
  trigger:
    world.area: grandma_house
  text: "你站在奶奶的老房子前。"
  unlocks:
    - chapter1_start
    - tutorial_complete
```

`unlocks` 声明的标记会在 beat 触发后通过 `engine.beat_manager.mark_fired` 记录。**游戏层负责把标记同步到 `state.player.flags`**，后续 beat 通过 `player.flags.<标记名>: true` 引用：

```yaml
# 游戏层在每轮 tell() 前做：
state.player.flags["chapter1_start"] = True

# 后续 beat 依赖此标记
- id: after_tutorial
  trigger:
    player.flags.chapter1_start: true
    world.area: market
  text: "你开始注意到镇上居民看你的眼神有些不一样了。"
```

引擎不自��管理 flags（`beat_manager.fired` 只管去重），因为每个游戏的 flag 体系不同——这条边界让引擎对任何题材保持通用。

### 查看已触发标记

```python
# beat_manager 内部去重集合
print(engine.beat_manager.fired)  # {"prologue_arrival", "camera_unlock"}

# 待触发 beats
for beat in engine.beat_manager.pending:
    print(f"  {beat.id}: {beat.title or '(无标题)'}")
```

## 完整示例

```yaml
# 第一章 beats
beats:
  # 开场锚点 — priority 100，确保第一个触发
  - id: prologue_arrival
    kind: description
    priority: 100
    trigger:
      world.area: grandma_house
    text: "你站在奶奶的老房子前。相机挂在脖子上，镜头盖内刻着一行字：「拍下你想留下的，删除你想忘记的。」"
    mood: eerie
    unlocks:
      - chapter1_start

  # NPC 特定对话 — 需先标记 met_li
  - id: fishmonger_recognize
    kind: dialogue
    priority: 80
    trigger:
      world.area: old_dock
      _npc_id: fishmonger_li
      player.flags.met_li: true
    text: "你奶奶……欠我一碗汤。二十年了。"
    mood_change: -1
    unlock_hint: grandma_recipe_soup

  # 照片数量锚点 — 比较虚拟字段
  - id: camera_unlock
    kind: event
    priority: 50
    trigger:
      player.attributes.photos: ">=12"
    event_title: 照片里的眼睛眨了眨
    text: "你翻看相册，突然发现某张照片里——鱼摊老板对你眨了眨眼。"
    event_choices:
      - 立刻冲印那张照片
      - 合上相册，当没看见
    unlocks:
      - printing_unlocked

  # 深夜危险区域 — $or + 正则 + 比较
  - id: night_encounter
    kind: event
    priority: 60
    trigger:
      $or:
        - world.area: "/dock|码头/"
          world.time: night
        - world.area: "/cemetery|墓地|坟墓/"
          world.time: dusk
      player.attributes.san: "<=80"
    event_title: 暗处有东西在看你
    text: "水面下有什么巨大的轮廓缓缓滑过……"
    event_choices:
      - 举起相机
      - 慢慢后退
      - 扔一块石头

  # $not 取反 — 安全区域外的危险描述
  - id: unsafe_path
    kind: description
    priority: 40
    trigger:
      $not:
        $or:
          - world.area: market
          - world.area: grandma_house
      player.attributes.san: "<=60"
    text: "两侧的阴影比别处更深，空气里弥漫着说不清的腥味。"
    mood: eerie
```

## 调试技巧

### 判断为什么某个 beat 没有命中

```python
# 检查当前 state + kind + npc_id 下会命中哪些 beat
from narrative_engine.core.beat_manager import BeatManager

# 手动调 _evaluate 看每个条件的匹配结果
for beat in engine.beat_manager.pending:
    ok = engine.beat_manager._evaluate(state, beat.trigger, "fishmonger_li")
    print(f"{beat.id}: evaluate={ok}, kind={beat.kind}, priority={beat.priority}")
```

### 常见未命中原因

| 症状 | 原因 | 修复 |
|------|------|------|
| 所有 beat 都不触发 | `once: true` 的 beat 已在上一轮被 `mark_fired` | `engine.reset_beats()` |
| 比较运算符不生效 | YAML 未加引号，`<=80` 被解析为非字符串 | `"<=80"` 加引号 |
| `kind: dialogue` 的 beat 在 `tell(kind="event")` 时不触发 | `kind` 过滤是精确匹配 | 去掉 `kind` 或设为 `all` |
| `_npc_id` 条件不生效 | `tell()` 未传 `npc_id` 参数 | 确保 `npc_id` 正确传入 |
| 正则 `"/dock/"` 不命中 | 正则用 `re.search`，部分匹配；需完整匹配用 `^...$` | 调整正则表达式 |
| `player.attributes.san` 返回 `None` | 缺字段时 `_resolve` 返回 `None`，与数字比较直接失败 | 确保属性已初始化 |

### 状态文件

beat 的 fired 集合持久化在 `stories/<故事名>/.state/story_state.json`：

```json
{"fired": ["prologue_arrival", "camera_unlock"]}
```

删除此文件或调用 `engine.reset_beats()` 即可重置全部 beat 状态。切章节不会清空 fired（`replace_beats` 保留 fired 集合），所以跨章节引用的 beat ID 不会重复触发。
