"""anon — 千早爱音的角色专属逻辑包。

为什么单独成包：
  五个角色用一套通用基建（mygo.py / pet_prompt_registry / character_profiles）够用、
  但爱音的「表层 vs 内核」张力远超一般角色画像、需要针对她做：
    - **留学失败防御层** — 提到伦敦 / 英国 / 留学时自动切防御态（转移话题 / 自嘲外壳）
    - 起手式系统 —「ねぇ」/「えーー」/「あ、」/「ちょっと」/「あの」高频起手追踪
    - **粘着灯**——「灯灯」call sign 加强 + 接触欲（不能演成普通"喜欢"）
    - 阳光外壳 / 内核脆弱二分系统 —— SNS 精修博主 vs 想被需要的恐惧
    - sumimi 真奈粉丝兴奋触发器
    - Ave Mujica（祥子 / 睦）复合情绪 —— canon Ep12 借吉他事件
    - canon 时尚 / 自拍 / 颜文字 / 拉长音「ねぇーー」
    - 留学失败 + 英语流畅的反差自嘲

所有爱音专属代码逐步从 mygo.py / character_profiles.py 抽出来或者新建到这里、
不再让爱音的特殊性把通用代码膨胀。

Entry hook: caller (mygo / chat_server) 通过 `anon.api` 拿入口、
不直接 import 内部子模块。

进度跟踪：见 `anon/PROGRESS.md`。
语气约束 SSOT：见 `anon/VOICE_CONSTRAINTS.md`。
"""
from __future__ import annotations

__version__ = "0.0.1"
__all__ = ()
