#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Isolated behavioral tests for review cadence, feedback history and safe migration."""
import copy
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

import v2_core as core
import 结构复盘 as review
import 运行反馈 as feedback
import 事务

ROOT = Path(__file__).resolve().parent.parent


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='novel-review-feedback-')
        self.parent = Path(self.tmp.name)
        self.project = self.parent/'project'
        self.run_cli(ROOT, 'init', str(self.project))
        data = core.load_project(str(self.project))
        data['initialization'] = {'status': 'legacy'}
        core.atomic_write_json(str(self.project/'project.json'), data)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, root, *args, good=True):
        result = subprocess.run([sys.executable, '-B', str(root/'novel.py'), *args], cwd=root,
                                capture_output=True, text=True)
        if good:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def chapters(self, count, ids=None):
        ids = ids or ['K%04d' % (i+1) for i in range(count)]
        lines = ['# 分章大纲', '| 永久 ID | 展示章号 | 视角 | 事件 | 开始 | 结束 | 状态 |', '|---|---|---|---|---|---|---|']
        for number, kid in enumerate(ids[:count], 1):
            lines.append('| %s | %d | 人物 | 事件 | 起点 | 终点 | 已定稿 |' % (kid, number))
            (self.project/('05_正文/'+kid+'.md')).write_text('# '+kid+'\n独立测试正文 '+kid+'\n')
        (self.project/review.OUTLINE).write_text('\n'.join(lines)+'\n')

    def finish(self, scope, state='已复盘', market='已完成'):
        self.run_cli(self.project, 'outline', '--prepare', '--scope', scope)
        root = self.project/'_候选/REVISE'
        path = root/review.RECORD
        text = path.read_text().replace('| 复盘状态 | 待复盘 |', '| 复盘状态 | '+state+' |')
        text = self.interview_answer(text)
        if scope == 'large':
            text = text.replace('| 榜单研究状态 | 未开始 |','| 榜单研究状态 | '+market+' |')
            text = text.replace('| 榜单研究依据 | |','| 榜单研究依据 | 隔离测试的访问记录与实际范围，非真实研究 |')
            text = text.replace('| 研究受限与补查条件 | |','| 研究受限与补查条件 | 测试访问受限；下次可访问时补查，既有路线继续 |')
        review.parse_record(text.encode())
        # Direct fixture setup only; real formal review still uses the tested REVISE transaction.
        (self.project/review.RECORD).write_text(text)
        import shutil
        shutil.rmtree(root)

    def interview_answer(self, text, state='已交流'):
        fields = {'作者访谈状态': state,
            '作者访谈依据': '隔离测试的模拟答复，只用于验证状态转换，非真实作者反馈',
            '作者意见处理': '测试沿用现有安排，下轮核对人物选择；不代表文学效果'}
        if '| 下一段加强措施 |' in text:      # 4.0 模板新增栏；旧记录不补造
            fields['下一段加强措施'] = '测试：下一批让对手先出手，非真实安排'
        return review.with_fields(text, fields)

    def test_v40_review_requires_next_strengthening_or_reasoned_keep(self):
        self.chapters(3)
        self.run_cli(self.project, 'outline', '--prepare')
        text = review.with_fields(self.interview_answer(
            (self.project/'_候选/REVISE'/review.RECORD).read_text()), {'复盘状态': '已复盘'})
        review.parse_record(text.encode())
        for bad in ('', '无', '以后'):
            with self.subTest(bad=bad), self.assertRaises(core.ProjectError):
                review.parse_record(review.with_fields(text, {'下一段加强措施': bad}).encode())
        kept = review.with_fields(text, {'下一段加强措施': '保留：本段的慢是有意铺垫，下一批兑现'})
        review.parse_record(kept.encode())

    def test_v40_large_review_may_skip_market_research_with_reason(self):
        self.chapters(12)
        self.run_cli(self.project, 'outline', '--prepare')
        text = review.with_fields(self.interview_answer(
            (self.project/'_候选/REVISE'/review.RECORD).read_text()),
            {'复盘状态': '已复盘', '榜单研究状态': '本轮不做'})
        with self.assertRaises(core.ProjectError):
            review.parse_record(text.encode())
        review.parse_record(review.with_fields(
            text, {'榜单研究依据': '作者决定本弧只看平台完读数据，不做榜单研究'}).encode())

    def test_fixed_boundaries_and_large_precedence(self):
        for count, expected in ((0,None),(2,None),(3,'small'),(6,'small'),(9,'small'),(12,'large'),(13,'large'),(24,'large')):
            with self.subTest(count=count):
                self.chapters(count)
                self.assertEqual(review.cycle_status(str(self.project))['scope'], expected)

    def test_nonsequential_ids_and_reorder_invalidate_coverage(self):
        ids=['K0400','K0002','K9000']
        self.chapters(3, ids)
        self.finish('small')
        self.assertIsNone(review.cycle_status(str(self.project))['scope'])
        self.chapters(3, list(reversed(ids)))
        state=review.cycle_status(str(self.project))
        self.assertEqual(state['scope'],'small')
        self.assertIn('small',state['stale'])

    def test_small_does_not_reset_large_and_late_review_keeps_grid(self):
        self.chapters(5);self.finish('small')
        self.chapters(6)
        self.assertEqual(review.cycle_status(str(self.project))['scope'],'small')
        self.chapters(9);self.finish('small')
        self.chapters(12)
        self.assertEqual(review.cycle_status(str(self.project))['scope'],'large')
        self.finish('large')
        state=review.cycle_status(str(self.project))
        self.assertIsNone(state['scope'])
        self.assertEqual(state['covered'],{'small':12,'large':12})
        self.assertEqual((state['next_small'],state['next_large']),(15,24))

    def test_prior_text_revision_reopens_review(self):
        self.chapters(3);self.finish('small')
        (self.project/'05_正文/K0002.md').write_text('修订后的独立测试正文')
        self.assertEqual(review.cycle_status(str(self.project))['scope'],'small')
        self.assertIn('旧结论需重查',review.cycle_summary(str(self.project)))

    def test_prepare_and_defer_do_not_claim_completion(self):
        self.chapters(3)
        before=(self.project/review.OUTLINE).read_bytes()
        self.run_cli(self.project,'outline','--prepare')
        self.assertFalse((self.project/review.RECORD).exists())
        self.assertEqual(review.cycle_status(str(self.project))['scope'],'small')
        self.run_cli(self.project,'outline','--refresh')
        candidate=self.project/'_候选/REVISE'/review.RECORD
        self.assertEqual(review.parse_record(candidate.read_bytes())[1]['复盘状态'],'待复盘')
        self.assertEqual((self.project/review.OUTLINE).read_bytes(),before)

    def test_history_survives_next_prepare(self):
        self.chapters(3);self.finish('small')
        old=(self.project/review.RECORD).read_bytes()
        self.chapters(6)
        self.run_cli(self.project,'outline','--prepare')
        archive=list((self.project/'_候选/REVISE/06_归档').glob('修订记录_结构复盘_*.md'))
        self.assertEqual(len(archive),1)
        self.assertEqual(archive[0].read_bytes(),old)
        self.assertEqual(review.cycle_status(str(self.project))['covered']['small'],3)

    def test_legacy_record_does_not_invent_new_research(self):
        self.chapters(12)
        text=review.with_basis((self.project/review.TEMPLATE).read_text(),review.snapshot(str(self.project)))
        text=text.replace('| 复盘状态 | 待复盘 |','| 复盘状态 | 已复盘 |')
        (self.project/review.RECORD).write_text(text)
        self.assertEqual(review.cycle_status(str(self.project))['scope'],'large')
        self.assertEqual(review.cycle_status(str(self.project))['covered']['large'],0)

    def test_large_completion_requires_research_or_explicit_limit(self):
        self.chapters(12)
        self.run_cli(self.project,'outline','--prepare')
        candidate=self.project/'_候选/REVISE'/review.RECORD
        text=candidate.read_text().replace('| 复盘状态 | 待复盘 |','| 复盘状态 | 已复盘 |')
        with self.assertRaises(core.ProjectError): review.parse_record(text.encode())
        text=text.replace('| 榜单研究状态 | 未开始 |','| 榜单研究状态 | 受限 |')
        text=text.replace('| 榜单研究依据 | |','| 榜单研究依据 | 已尝试访问的范围 |')
        with self.assertRaises(core.ProjectError): review.parse_record(text.encode())
        text=text.replace('| 研究受限与补查条件 | |','| 研究受限与补查条件 | 原因、继续范围和补查条件 |')
        text=self.interview_answer(text)
        review.parse_record(text.encode())
        (self.project/review.RECORD).write_text(text)
        self.assertIn('补查仍待跟进',review.summary(str(self.project)))

    def test_limited_research_debt_survives_small_review(self):
        self.chapters(12);self.finish('large', market='受限')
        self.chapters(15);self.finish('small')
        self.assertIn('补查仍待跟进',review.summary(str(self.project)))
        self.assertEqual(review.cycle_status(str(self.project))['covered']['large'],12)

    def test_prompt_is_readonly_and_assigns_real_content_research(self):
        self.chapters(12)
        before=self.fingerprint()
        output=self.run_cli(self.project,'outline','--prompt')
        for word in ('实际联网','至少两种','实际章段','不能以榜单名','05_正文/K0001.md','05_正文/K0012.md','原大纲'):
            self.assertIn(word,output)
        self.assertEqual(self.fingerprint(),before)
        self.assertIn('十二章大审查',review.pack_note(str(self.project)))
        self.assertIsNone(review.with_pack_note(str(self.project),None))

    def fingerprint(self):
        return {str(p.relative_to(self.project)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.project.rglob('*') if p.is_file()}

    def event(self):
        return {'issue_id':'ISS-test','kind':'写作质量','status':'待分析','summary':'隔离测试中的阅读问题',
                'source':{'kind':'当前对话','locator':'隔离测试消息','excerpt':'测试反馈原句','coverage':'只覆盖此测试消息'},
                'analysis':'原判断及疑点','action':'尚未执行，提出局部调整','verification':'未验证',
                'decision':'先验证是否为通用问题','scope':'仅本隔离测试'}

    def write_event(self,event,good=True):
        source=self.parent/'event.json';source.write_text(json.dumps(event,ensure_ascii=False))
        return self.run_cli(self.project,'feedback','--record',str(source),good=good)

    def test_feedback_append_dedup_reopen_and_no_story_head(self):
        event=self.event();before=self.fingerprint()
        self.write_event(event)
        first=(self.project/feedback.RECORD).read_bytes()
        self.write_event(event)
        self.assertEqual(first,(self.project/feedback.RECORD).read_bytes())
        event['status']='待验证';event['action']='实施测试修订并等待阅读反馈';self.write_event(event)
        event['status']='重新打开';event['source']['excerpt']='后续反馈仍然存在问题';self.write_event(event)
        items=feedback.events(str(self.project));self.assertEqual(len(items),3)
        self.assertEqual(items[0]['status'],'待分析')
        self.assertEqual(feedback.latest(str(self.project))['ISS-test']['status'],'重新打开')
        after=self.fingerprint()
        self.assertTrue(all(after[k]==v for k,v in before.items()))
        self.assertFalse((self.project/'.novel/HEAD').exists())
        output=self.run_cli(self.project,'feedback','--issue','ISS-test')
        self.assertIn('测试反馈原句',output);self.assertIn('后续反馈仍然存在问题',output)

    def test_feedback_rejects_missing_provenance_and_false_closed_state(self):
        for mutate in (lambda x:x['source'].pop('coverage'),lambda x:x.update(status='已解决'),lambda x:x.update(issue_id='../bad')):
            event=self.event();mutate(event);self.write_event(event,good=False)
        self.assertFalse((self.project/feedback.RECORD).exists())

    def test_feedback_tamper_is_reported_and_backup_preserves_history(self):
        self.write_event(self.event())
        self.run_cli(self.project,'backup')
        archive=next((self.project/'_备份').glob('*.tar.gz'))
        with tarfile.open(archive) as z:
            self.assertEqual(z.extractfile(feedback.RECORD).read(),(self.project/feedback.RECORD).read_bytes())
        path=self.project/feedback.RECORD;path.write_text(path.read_text().replace('原判断及疑点','未记录的改动'))
        output=self.run_cli(self.project,'feedback',good=False)
        self.assertIn('摘要不一致',output)

    def test_feedback_link_and_pending_transaction_are_rejected(self):
        outside=self.parent/'outside.jsonl';outside.write_text('external')
        (self.project/feedback.RECORD).symlink_to(outside)
        self.write_event(self.event(),good=False)
        self.assertEqual(outside.read_text(),'external')
        (self.project/feedback.RECORD).unlink()
        (self.project/'.novel/transaction.json').write_text(json.dumps({'files':['README.md'],'id':'pending-test','phase':'prepared'}))
        self.write_event(self.event(),good=False)
        self.assertFalse((self.project/feedback.RECORD).exists())

    def test_sync_detects_local_change_and_explicit_keep_preserves_it(self):
        rel='README.md';path=self.project/rel;path.write_text('本项目修改')
        before=self.fingerprint()
        output=self.run_cli(ROOT,'sync',str(self.project),'--check',good=False)
        self.assertIn('本地修改',output);self.assertEqual(before,self.fingerprint())
        self.run_cli(ROOT,'sync',str(self.project),'--keep-local',rel)
        self.assertEqual(path.read_text(),'本项目修改')
        self.run_cli(ROOT,'sync',str(self.project),good=False)

    def test_sync_unknown_baseline_does_not_overwrite(self):
        data=core.load_project(str(self.project));data.pop('system_file_hashes');data['system_version']='2.0.0'
        core.atomic_write_json(str(self.project/'project.json'),data)
        (self.project/'README.md').write_text('无法证明归属的旧内容')
        self.run_cli(ROOT,'sync',str(self.project),good=False)
        self.assertEqual((self.project/'README.md').read_text(),'无法证明归属的旧内容')

    def test_custom_plugin_and_installed_rule_are_preserved(self):
        self.run_cli(self.project,'plugin','install','serial',str(self.project))
        rel='04_题材插件/_包/网文连载/plugin.json'
        path=self.project/rel;m=json.loads(path.read_text());m['version']='3.7.0-book-test.1';path.write_text(json.dumps(m,ensure_ascii=False))
        data=core.load_project(str(self.project));data['plugin_version']['serial']=m['version'];core.atomic_write_json(str(self.project/'project.json'),data)
        check=self.project/'02_检查层/插件/serial.md';check.write_text('本书定制检查')
        manual=self.project/'04_题材插件/网文连载.md';manual.write_text('本书定制手册')
        before=path.read_bytes();self.run_cli(ROOT,'sync',str(self.project))
        self.assertEqual(path.read_bytes(),before);self.assertEqual(check.read_text(),'本书定制检查')
        self.assertEqual(manual.read_text(),'本书定制手册')
        self.assertEqual(core.load_project(str(self.project))['plugin_version']['serial'],m['version'])
        # Run verification from the mother entry point to catch accidental use of the mother's package.
        check.write_bytes((ROOT/'04_题材插件/_包/网文连载/templates/02_检查层/插件/serial.md').read_bytes())
        self.run_cli(ROOT,'plugin','verify','serial',str(self.project))

    def test_shared_plugin_local_edits_require_explicit_decision(self):
        self.run_cli(self.project,'plugin','install','serial',str(self.project))
        rel='02_检查层/插件/serial.md';path=self.project/rel;path.write_text('定制内容')
        self.run_cli(ROOT,'sync',str(self.project),good=False)
        self.run_cli(ROOT,'sync',str(self.project),'--keep-local',rel)
        self.assertEqual(path.read_text(),'定制内容')

    def test_master_has_no_filled_operational_data(self):
        self.assertFalse((ROOT/feedback.RECORD).exists())
        self.assertFalse((ROOT/review.RECORD).exists())
        self.assertFalse((self.project/'_工具/阶段反馈自测.py').exists())

    def test_reading_pages_are_clean_complete_and_readonly(self):
        self.chapters(12)
        body = self.project/'05_正文/K0001.md'
        body.write_text('<!-- 永久ID:K0001 | 状态:已定稿 -->\n# 第一章\n正文中的<!-- 保留文字 -->\n')
        (self.project/'06_归档/章节卡_K0001.md').write_text('CARD_SENTINEL_NOT_PROSE')
        before = self.fingerprint()
        outputs = [self.run_cli(self.project, 'outline', '--reading', '--scope', 'large',
                                '--offset', str(n), '--limit', '4') for n in (0, 4, 8)]
        self.assertEqual(self.fingerprint(), before)
        all_output = '\n'.join(outputs)
        self.assertNotIn('永久ID:', all_output)
        self.assertNotIn('CARD_SENTINEL_NOT_PROSE', all_output)
        self.assertIn('<!-- 保留文字 -->', all_output)
        self.assertIn('# 第一章', all_output)
        self.assertEqual(len(re.findall(r'--- DATA 05_正文/K\d{4}\.md', all_output)), 12)
        self.assertIn('尚有 8 章未输出', outputs[0])
        self.assertIn('已到本范围末尾', outputs[2])
        self.assertIn('本次仅输出第 9 至 12 章', outputs[2])
        self.assertNotIn('本轮正文已全部输出', outputs[2])

    def test_reading_last_page_does_not_claim_previous_coverage(self):
        self.chapters(12)
        before = self.fingerprint()
        output = self.run_cli(self.project, 'outline', '--reading', '--scope', 'large',
                              '--offset', '8', '--limit', '4')
        self.assertEqual(re.findall(r'--- DATA 05_正文/(K\d{4})\.md', output),
                         ['K0009', 'K0010', 'K0011', 'K0012'])
        self.assertIn('本次仅输出第 9 至 12 章', output)
        self.assertIn('前 8 章是否已输出或读完须核对实际记录', output)
        self.assertIn('输出不证明已读完', output)
        self.assertNotIn('本范围全部', output)
        self.assertNotIn('本轮正文已全部输出', output)
        self.assertEqual(self.fingerprint(), before)

    def test_reading_whole_range_and_end_offset_are_readonly(self):
        self.chapters(3)
        before = self.fingerprint()
        output = self.run_cli(self.project, 'outline', '--reading', '--scope', 'large',
                              '--limit', '12')
        self.assertEqual(len(re.findall(r'--- DATA 05_正文/K\d{4}\.md', output)), 3)
        self.assertIn('本次已输出本范围全部 3 章', output)
        self.assertIn('输出不证明已读完', output)
        self.assertNotIn('前 0 章', output)
        end = self.run_cli(self.project, 'outline', '--reading', '--scope', 'large',
                           '--offset', '3', '--limit', '4', good=False)
        self.assertIn('偏移超出范围', end)
        self.assertNotIn('--- DATA', end)
        self.assertNotIn('本范围全部', end)
        self.assertEqual(self.fingerprint(), before)

    def test_reading_preserves_display_order_and_boundary(self):
        ids = ['K0300', 'K0010', 'K7000', 'K0002', 'K0050', 'K9000']
        self.chapters(3, ids); self.finish('small')
        self.chapters(6, ids)
        output = self.run_cli(self.project, 'outline', '--reading')
        found = re.findall(r'--- DATA 05_正文/(K\d{4})\.md', output)
        self.assertEqual(found, ids[2:])

    def test_reading_invalid_parameters_and_sources_fail(self):
        self.chapters(3)
        for args in [('--limit', '0'), ('--offset', '-1'), ('--offset', '3'), ('--limit', '13')]:
            self.run_cli(self.project, 'outline', '--reading', *args, good=False)
        self.run_cli(self.project, 'outline', '--prompt', '--limit', '2', good=False)
        path = self.project/'05_正文/K0002.md'
        path.write_bytes(b'\xff')
        self.assertIn('UTF-8', self.run_cli(self.project, 'outline', '--reading', good=False))
        path.unlink()
        self.run_cli(self.project, 'outline', '--reading', good=False)
        outside = self.parent/'outside.md'; outside.write_text('外部不可读入正文')
        path.symlink_to(outside)
        self.run_cli(self.project, 'outline', '--reading', good=False)

    def test_quality_followups_latest_state_and_bounded_pack(self):
        for n in range(5):
            event = self.event(); event['issue_id'] = 'ISS-test%d' % n
            event['summary'] = 'DATA_SENTINEL_' + str(n)
            self.write_event(event)
        event = self.event(); event['issue_id'] = 'ISS-test0'; event['status'] = '重新打开'
        self.write_event(event)
        event = self.event(); event['issue_id'] = 'ISS-test4'
        event['status'] = '已解决'; event['verification'] = '仅本隔离测试的已验证结果'
        self.write_event(event)
        items, total = feedback.quality_followups(str(self.project))
        self.assertEqual(total, 4)
        self.assertEqual([item['issue_id'] for item in items], ['ISS-test0', 'ISS-test3', 'ISS-test2'])
        note = review.pack_note(str(self.project))
        self.assertNotIn('DATA_SENTINEL_', note)
        self.assertNotIn('ISS-test4', note)
        self.assertIn('ISS-test0', note)
        output = self.run_cli(self.project, 'outline', '--prompt')
        self.assertIn('质量线索 DATA', output)
        self.assertIn('当前重复', output)
        self.assertNotIn('DATA_SENTINEL_4', output)

    def revision_fixture(self):
        import 新书自测 as fixture
        fixture.填全(str(self.project))
        rel = '00_设定层/01_固定设定.md'
        self.run_cli(self.project, 'revise', '--prepare', '--file', rel)
        candidate = self.project/'_候选/REVISE'/rel
        candidate.write_text(candidate.read_text() + '\n补充隔离测试说明。\n')
        self.run_cli(self.project, 'revise', '--review')
        path = self.project/'_候选/REVISE_关联核对.json'
        data = json.loads(path.read_text())
        for row in data['items']:
            row['status'] = '已核对'; row['note'] = '测试夹具仅补说明，既有记录保持。'
        path.write_text(json.dumps(data, ensure_ascii=False))
        output = self.run_cli(self.project, 'revise')
        return re.search(r'REVISION_SHA256=([0-9a-f]{64})', output).group(1), candidate

    def test_feedback_append_keeps_revision_approval_and_survives_rollback(self):
        digest, _ = self.revision_fixture()
        self.write_event(self.event())
        log = (self.project/feedback.RECORD).read_bytes()
        output = self.run_cli(self.project, 'revise')
        self.assertIn('REVISION_SHA256=' + digest, output)
        self.run_cli(self.project, 'revise', '--apply', '--approve', digest)
        self.assertEqual((self.project/feedback.RECORD).read_bytes(), log)
        self.run_cli(self.project, 'rollback')
        self.assertEqual((self.project/feedback.RECORD).read_bytes(), log)

    def test_story_and_candidate_changes_still_invalidate_approval(self):
        digest, candidate = self.revision_fixture()
        self.write_event(self.event())
        original = candidate.read_bytes()
        candidate.write_text(candidate.read_text() + '\n不同的候选内容。\n')
        self.assertIn('失效', self.run_cli(self.project, 'revise', '--apply', '--approve', digest, good=False))
        candidate.write_bytes(original)
        fact = self.project/'01_运行层/06_事实记录.md'
        fact.write_text(fact.read_text() + '\n不同的正式故事记录。\n')
        self.assertIn('失效', self.run_cli(self.project, 'revise', '--apply', '--approve', digest, good=False))

    def test_corrupt_log_and_revision_log_target_are_rejected(self):
        import 修订 as revision
        self.write_event(self.event())
        path = self.project/feedback.RECORD; original = path.read_bytes()
        for damaged in [b'\xff', original.replace('原判断及疑点'.encode(), '伪造新判断'.encode())]:
            path.write_bytes(damaged)
            with self.assertRaises(core.ProjectError): revision.baseline(str(self.project))
        path.write_bytes(original)
        self.run_cli(self.project, 'revise', '--prepare', '--file', feedback.RECORD, good=False)
        path.unlink(); outside = self.parent/'log.jsonl'; outside.write_bytes(original)
        path.symlink_to(outside)
        with self.assertRaises(core.ProjectError): revision.baseline(str(self.project))

    def test_voice_prompt_compares_attention_and_sample_scope(self):
        output = self.run_cli(self.project, 'voice', '--prompt')
        self.assertIn('人物注意什么', output)
        self.assertIn('不把其中的道具', output)
        self.assertIn('不增加固定试写轮次', output)

    def test_exploration_is_not_pending_submission(self):
        self.run_cli(self.project, 'plugin', 'none')
        folder = self.project/'_候选/探索'; folder.mkdir(parents=True)
        (folder/'历史.md').write_text('应保留的探索记录')
        output = self.run_cli(self.project, 'status')
        self.assertIn('探索资料', output)
        self.assertNotIn('试算或删除', output)
        self.assertNotIn('未处理候选', output)
        output = self.run_cli(self.project, 'doctor')
        self.assertNotIn('候选提交仍未处理', output)
        (self.project/'_候选/K0001').mkdir()
        self.assertIn('未处理候选', self.run_cli(self.project, 'status'))

    def test_baseline_tracks_approved_sources_not_all_chapters(self):
        import 文风 as style
        self.chapters(3)
        self.assertEqual(style.基线提醒(str(self.project))[0], '语料不足')
        sample = self.project/'00_设定层/02_风格样本.md'
        sample.write_text('# 风格\n## A. 正样本\n```text\n' + '测试人物走到窗边。' * 300 +
                          '\n```\n## E. 认可章节\n| 认可为文风样本的章节 | K0001 |\n')
        baseline, detail = style.建基线(str(self.project))
        (self.project/style.基线rel).write_text(style.基线区块(baseline, detail))
        self.assertEqual(style.基线提醒(str(self.project)), ('已建立', ''))
        self.chapters(6)
        self.assertEqual(style.基线提醒(str(self.project)), ('已建立', ''))
        (self.project/'05_正文/K0002.md').write_text('未认可正文改变')
        self.assertEqual(style.基线提醒(str(self.project)), ('已建立', ''))
        (self.project/'05_正文/K0001.md').write_text('已认可正文改变')
        self.assertEqual(style.基线提醒(str(self.project))[0], '需更新')
        sample.write_text(sample.read_text().replace('| K0001 |', '| |'))
        self.assertEqual(style.基线提醒(str(self.project))[0], '需更新')

    def test_style_match_is_not_an_automatic_rewrite_order(self):
        import 文风 as style
        prompt = style.改写提示词('K0001', [('测试类', '原句', 1, '一行样例', '词')], [], None)
        self.assertIn('命中不等于错误', prompt)
        self.assertIn('不统一替换成小动作', prompt)
        self.assertNotIn('逐行改写', prompt)

    def test_interview_waiting_is_not_completed_review(self):
        self.chapters(3)
        self.run_cli(self.project, 'outline', '--prepare')
        path = self.project/'_候选/REVISE'/review.RECORD
        text = path.read_text()
        for state in ('待访谈', '待作者回复', '待核对', '不适用'):
            proposed = review.with_fields(text, {'复盘状态': '已复盘', '作者访谈状态': state})
            with self.subTest(state=state), self.assertRaises(core.ProjectError):
                review.parse_record(proposed.encode())
        path.write_text(review.with_fields(text, {'作者访谈状态': '待作者回复'}))
        self.assertIn('待作者回复', self.run_cli(self.project, 'outline'))
        self.assertEqual(review.cycle_status(str(self.project))['covered']['small'], 0)
        self.assertFalse((self.project/review.RECORD).exists())

    def test_interview_resolved_states_require_source_and_treatment(self):
        self.chapters(3)
        self.run_cli(self.project, 'outline', '--prepare')
        text = (self.project/'_候选/REVISE'/review.RECORD).read_text()
        for state in review.INTERVIEW_DONE:
            complete = review.with_fields(self.interview_answer(text, state), {'复盘状态': '已复盘'})
            self.assertEqual(review.parse_record(complete.encode())[1]['作者访谈状态'], state)
            for key in ('作者访谈依据', '作者意见处理'):
                with self.subTest(state=state, key=key), self.assertRaises(core.ProjectError):
                    review.parse_record(review.with_fields(complete, {key: ''}).encode())
        with self.assertRaises(core.ProjectError):
            review.parse_record(review.with_fields(text, {'作者访谈状态': '模型代答'}).encode())

    def test_refresh_preserves_answers_and_rechecks_changed_basis(self):
        self.chapters(3)
        self.run_cli(self.project, 'outline', '--prepare')
        path = self.project/'_候选/REVISE'/review.RECORD
        text = review.with_fields(self.interview_answer(path.read_text()), {'复盘状态': '已复盘'})
        path.write_text(text + '\n原始答复必须保留的测试标记\n')
        self.run_cli(self.project, 'outline', '--refresh')
        self.assertEqual(review.parse_record(path.read_bytes())[1]['作者访谈状态'], '已交流')
        (self.project/'05_正文/K0002.md').write_text('修改了已读测试版本')
        output = self.run_cli(self.project, 'outline', '--interview')
        self.assertIn('依据或范围已变化', output)
        self.run_cli(self.project, 'outline', '--refresh')
        _, fields, _ = review.parse_record(path.read_bytes())
        self.assertEqual(fields['作者访谈状态'], '待核对')
        self.assertIn('模拟答复', fields['作者访谈依据'])
        self.assertIn('原始答复必须保留', path.read_text())

    def test_new_round_does_not_inherit_interview_or_duplicate_large(self):
        self.chapters(3); self.finish('small')
        self.chapters(6); self.run_cli(self.project, 'outline', '--prepare')
        text = (self.project/'_候选/REVISE'/review.RECORD).read_text()
        self.assertEqual(review.parse_record(text.encode())[1]['作者访谈状态'], '待访谈')
        self.assertNotIn('模拟答复', text)
        output = self.run_cli(self.project, 'outline', '--prompt', '--scope', 'large')
        self.assertEqual(output.count('阶段作者访谈任务｜'), 1)
        self.assertIn('实际联网', output)
        self.assertIn('依据或范围已变化', output)

    def test_interview_command_readonly_and_no_fabricated_summary(self):
        self.chapters(3)
        sentinel = '正文内容不能被任务提示冒充已读'
        (self.project/'05_正文/K0001.md').write_text(sentinel)
        before = self.fingerprint()
        output = self.run_cli(self.project, 'outline', '--interview')
        self.assertEqual(self.fingerprint(), before)
        self.assertNotIn(sentinel, output)
        self.assertIn('命令未阅读、未提问、未收集答复', output)
        self.assertIn('等待实际答复', output)
        self.run_cli(self.project, 'outline', '--interview', '--limit', '2', good=False)

    def test_opening_no_interview_and_legacy_completion_stays_readable(self):
        data = core.load_project(str(self.project))
        data['initialization'] = {'status': 'draft'}
        core.atomic_write_json(str(self.project/'project.json'), data)
        self.run_cli(self.project, 'outline', '--prepare')
        path = self.project/'_候选/INIT'/review.RECORD
        self.assertEqual(review.parse_record(path.read_bytes())[1]['作者访谈状态'], '不适用')
        self.assertIn('开书论证沿用', self.run_cli(self.project, 'outline', '--interview'))
        self.assertNotIn('阶段作者访谈任务｜', self.run_cli(self.project, 'outline', '--prompt'))
        data['initialization'] = {'status': 'legacy'}
        core.atomic_write_json(str(self.project/'project.json'), data)
        self.chapters(3); self.finish('small')
        formal = self.project/review.RECORD
        old = '\n'.join(line for line in formal.read_text().splitlines()
                        if not any(line.startswith('| '+key+' |') for key in ('作者访谈状态','作者访谈依据','作者意见处理')))+'\n'
        formal.write_text(old)
        self.assertNotIn('作者访谈状态', review.parse_record(formal.read_bytes())[1])
        self.assertEqual(review.cycle_status(str(self.project))['covered']['small'], 3)
        self.assertEqual(formal.read_text(), old)

    def test_feedback_correction_is_displayed_before_historical_pass(self):
        event = self.event(); event.update(status='已解决', verification='仅测试旧结论', summary='旧通过记录')
        self.write_event(event)
        first = (self.project/feedback.RECORD).read_bytes()
        event.update(status='重新打开', summary='已收窄的最新判断', verification='新报告与旧结论的范围差异，仅测试')
        self.write_event(event)
        output = self.run_cli(self.project, 'feedback', '--issue', event['issue_id'])
        self.assertLess(output.index('已收窄的最新判断'), output.index('旧通过记录'))
        self.assertTrue((self.project/feedback.RECORD).read_bytes().startswith(first))
        self.assertIn('不覆盖上方最新记录', output)

    def test_archived_pending_interview_resumes_same_round(self):
        self.chapters(3)
        self.run_cli(self.project, 'outline', '--prepare')
        root = self.project/'_候选/REVISE'
        path = root/review.RECORD
        text = review.with_fields(path.read_text(), {'作者访谈状态': '待作者回复'})
        text += '\n本轮已问的问题应保留，隔离测试记录。\n'
        (self.project/review.RECORD).write_text(text)
        import shutil
        shutil.rmtree(root)
        self.assertIn('同轮已记录等待答复', self.run_cli(self.project, 'outline', '--interview'))
        self.run_cli(self.project, 'outline', '--prepare')
        self.assertIn('本轮已问的问题应保留', path.read_text())
        self.assertEqual(review.parse_record(path.read_bytes())[1]['作者访谈状态'], '待作者回复')

    def test_added_future_plan_invalidates_existing_interview_scope(self):
        self.chapters(3)
        self.run_cli(self.project, 'outline', '--prepare')
        root = self.project/'_候选/REVISE'
        path = root/review.RECORD
        path.write_text(self.interview_answer(path.read_text()))
        outline = root/review.OUTLINE
        outline.write_text(outline.read_text() + '| K0004 | 4 | 人物 | 新的待写安排 | 起点 | 终点 | 未写 |\n')
        self.run_cli(self.project, 'outline', '--refresh')
        self.assertEqual(review.parse_record(path.read_bytes())[1]['作者访谈状态'], '待核对')

    def test_waiting_question_is_rechecked_after_prose_changes(self):
        self.chapters(3)
        self.run_cli(self.project, 'outline', '--prepare')
        path = self.project/'_候选/REVISE'/review.RECORD
        path.write_text(review.with_fields(path.read_text(), {'作者访谈状态': '待作者回复'}))
        (self.project/'05_正文/K0001.md').write_text('改变本轮问题背景的测试正文')
        self.run_cli(self.project, 'outline', '--refresh')
        self.assertEqual(review.parse_record(path.read_bytes())[1]['作者访谈状态'], '待核对')


if __name__ == '__main__':
    unittest.main(verbosity=2)
