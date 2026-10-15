import unittest
from coopanion_soft_voice.speech_text import split_speech_text, complete_native_piece


class SpeechTextTests(unittest.TestCase):
    def test_independent_clause_gets_an_end_without_losing_words(self):
        self.assertEqual(complete_native_piece('Core 会沿用系统代理（连 PAC 也读），'), 'Core 会沿用系统代理（连 PAC 也读）。')
        self.assertEqual(complete_native_piece('Core 使用系统代理'), 'Core 使用系统代理。')
        self.assertEqual(complete_native_piece('没有标点的分段'), '没有标点的分段')
        self.assertEqual(complete_native_piece('原有中文语气，'), '原有中文语气，')
        for text in ['我在这里陪你呀，慢慢来，不着急。', '你好！', '可以吗？']:
            self.assertEqual(complete_native_piece(text), text)

    def test_reported_reply_uses_natural_short_clauses_without_losing_text(self):
        text='可以这么比喻，但不是“死了又活过来”——我没有持续的主观体验，也不会在两次对话之间感到时间流逝。更准确地说，收到消息时系统才运行这一轮，生成回复；没人问时，我没有在后台醒着思考。'
        pieces=split_speech_text(text,32,24)
        self.assertEqual([len(s) for s in pieces],[20,28,25,16])
        self.assertEqual(''.join(pieces),text)
        self.assertTrue(pieces[0].endswith('——'))
        self.assertTrue(pieces[2].endswith('；'))

    def test_short_approved_utterance_is_unchanged(self):
        text='我在这里陪你呀，慢慢来，不着急。'
        self.assertEqual(split_speech_text(text,32,24),[text])

    def test_unpunctuated_text_and_trailing_space_are_bounded(self):
        pieces=split_speech_text('字'*100+'\n',32,24)
        self.assertEqual(''.join(pieces),'字'*100+'\n')
        self.assertTrue(all(len(s)<=32 for s in pieces))
        self.assertEqual(split_speech_text('字'*32+'\n',32,24),['字'*32])

    def test_invalid_limits_are_rejected(self):
        for limit,target in [(0,None),(32,33),(32,0),(True,None)]:
            with self.assertRaises(ValueError):split_speech_text('测试',limit,target)


if __name__=='__main__':unittest.main()
