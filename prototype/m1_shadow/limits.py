"""实验 D 之后的产品边界。

OpenPronounce 音素级精确率 0.148，低于事先定的 0.60。
设计文档里的 P 类 ErrorInstance、PhonemeProfile.accuracy_mean_30d、
common_substitution 都不能用这层输出填写。见
docs/design/2026-10-23-m1-risk-validation.md 第 6.6 节。
"""

PHONEME_PRODUCT_RULE = (
    "实验 D 未通过：OpenPronounce 音素级精确率 0.148"
    "（召回率 0.759，替换方向准确率 0.351）。"
    "因此这里不用音素标记产生 P 类 ErrorInstance，"
    "不填写 PhonemeProfile.accuracy_mean_30d，也不写 common_substitution。"
    "低分句只表示词级召回偏低，不是音素错误。"
    "本原型同样不把结果写入学习者模型。"
)

# 词召回低于这个比例才把句子标成低分。0.75 本身不算低分。
# 这是原型界面的显示门槛，不是 PhonemeProfile 的 0.85，也不是 ErrorInstance 的 0.6。
LOW_SCORE_RECALL = 0.75


def seal_no_phoneme_writes(payload: dict) -> dict:
    """接口边界上强制清掉学习者模型写入。

    调用方即使塞了音素结果，响应里也不保留。
    """

    payload["error_instances"] = []
    payload["phoneme_profile"] = None
    payload["common_substitution"] = None
    payload["phoneme_feedback"] = False
    payload["product_rule"] = PHONEME_PRODUCT_RULE
    return payload
