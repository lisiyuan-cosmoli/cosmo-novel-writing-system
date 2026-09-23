/* Progressive enhancement. Reading content remains available without JavaScript. */
(() => {
  'use strict';

  const english = document.documentElement.lang.toLowerCase().startsWith('en');
  const messages = english ? {
    copied: 'Copied. Paste this prompt into your AI workspace and send it.',
    copyFallback: 'Automatic copying failed. The prompt is selected; please copy it manually.',
    scenarios: {
      same: { title: 'Content and baseline match', draft: 'Version A', base: 'Original state', draftNote: 'Unchanged since approval', baseNote: 'Unchanged since the dry run', outcome: 'pass', result: 'Saving can proceed', note: 'Once the digest matches and required checks pass, the manuscript and related records are saved together.' },
      draft: { title: 'The candidate changed after approval', draft: 'Version B', base: 'Original state', draftNote: 'Different from the approved version A', baseNote: 'Unchanged since the dry run', outcome: 'stop', result: 'Pause, rerun the dry run, and approve again', note: 'The new draft has a new content digest. The earlier approval does not cover it.' },
      base: { title: 'Committed files changed after the dry run', draft: 'Version A', base: 'New state', draftNote: 'The candidate itself is unchanged', baseNote: 'Files involved in the change have been modified', outcome: 'stop', result: 'Pause and recheck against the current files', note: 'Resolve the baseline change, then rerun the dry run and obtain approval using the current evidence.' }
    }
  } : {
    copied: '已复制。粘贴到 AI 代理工作区并发送即可。',
    copyFallback: '自动复制未成功，提示词已选中，请手动复制。',
    scenarios: {
      same: { title: '内容与基线一致', draft: '版本 A', base: '原状态', draftNote: '与作者确认时相同', baseNote: '仍是试算时的状态', outcome: 'pass', result: '可以继续保存', note: '摘要匹配且必要检查通过后，正文与相关记录一起保存。' },
      draft: { title: '确认之后，候选稿又改了', draft: '版本 B', base: '原状态', draftNote: '已不同于作者确认的版本 A', baseNote: '仍是试算时的状态', outcome: 'stop', result: '暂停保存，重新试算与确认', note: '新稿有新的内容摘要，旧批准不适用于新稿。' },
      base: { title: '试算之后，相关正式文件变了', draft: '版本 A', base: '新状态', draftNote: '候选稿本身没有变化', baseNote: '参与修改的原文件已经变化', outcome: 'stop', result: '暂停保存，基于当前文件重新核对', note: '先处理基线变化，再重新试算并确认，避免沿用过时依据。' }
    }
  };

  document.querySelectorAll('[data-switch-group]').forEach(group => {
    const buttons = [...group.querySelectorAll('[data-panel]')];
    const panels = [...document.querySelectorAll('[data-panel-group]')]
      .filter(panel => panel.dataset.panelGroup === group.dataset.switchGroup);
    if (!buttons.length || buttons.some(button => !panels.some(panel => panel.id === button.dataset.panel))) return;
    function select(button) {
      buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      panels.forEach(panel => { panel.hidden = panel.id !== button.dataset.panel; });
    }
    buttons.forEach(button => button.addEventListener('click', () => select(button)));
    select(buttons[0]);
    group.hidden = false;
  });

  const scenarioGroup = document.querySelector('[data-scenarios]');
  if (scenarioGroup) {
    const comparison = document.getElementById('comparison');
    const scenarios = messages.scenarios;
    const buttons = [...scenarioGroup.querySelectorAll('[data-scenario]')];
    buttons.forEach(button => button.addEventListener('click', () => {
      const key = button.dataset.scenario;
      const data = scenarios[key];
      if (!data) return;
      buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      comparison.dataset.outcome = data.outcome;
      [['scenario-title', data.title], ['draft-version', data.draft], ['base-version', data.base],
       ['draft-description', data.draftNote], ['base-description', data.baseNote],
       ['result-title', data.result], ['result-description', data.note]].forEach(([id, value]) => {
        document.getElementById(id).textContent = value;
      });
      document.getElementById('draft-paper').classList.toggle('changed', key === 'draft');
      document.getElementById('base-paper').classList.toggle('changed', key === 'base');
    }));
    scenarioGroup.hidden = false;
    document.getElementById('scenario-fallback').hidden = true;
  }

  const copy = document.getElementById('copy-command');
  if (copy) {
    copy.hidden = false;
    copy.addEventListener('click', async () => {
      const code = document.getElementById('start-command');
      const status = document.getElementById('copy-status');
      try {
        if (!navigator.clipboard) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(code.textContent);
        status.textContent = messages.copied;
      } catch {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(code);
        if (selection) { selection.removeAllRanges(); selection.addRange(range); }
        status.textContent = messages.copyFallback;
      }
    });
  }
})();
