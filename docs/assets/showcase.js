/* Progressive enhancement. Reading content remains available without JavaScript. */
(() => {
  'use strict';

  const english = document.documentElement.lang.toLowerCase().startsWith('en');
  const messages = english ? {
    copied: 'Copied. Paste this prompt into your AI workspace and send it.',
    copyFallback: 'Automatic copying failed. The prompt is selected; please copy it manually.',
    scenarios: {
      same: { title: 'Everything matches what you approved', draft: 'Version A', base: 'Original state', draftNote: 'Same as when you approved it', baseNote: 'Same as during the dry run', outcome: 'pass', result: 'Ready to save', note: 'Once the digest matches and the required checks pass, the chapters and related records are written together.' },
      draft: { title: 'The draft changed after approval', draft: 'Version B', base: 'Original state', draftNote: 'No longer the version A you approved', baseNote: 'Same as during the dry run', outcome: 'stop', result: 'Saving paused: rerun the dry run and approve again', note: 'The new draft has a new content digest, so your earlier approval does not cover it.' },
      base: { title: 'Book files changed after the dry run', draft: 'Version A', base: 'New state', draftNote: 'The draft itself is unchanged', baseNote: 'Files involved in this change were modified', outcome: 'stop', result: 'Saving paused: recheck against the current files', note: 'Resolve the file changes first, then rerun the dry run and approve, so nothing is saved against an outdated state.' }
    }
  } : {
    copied: '已复制。粘贴到 AI 代理的工作区并发送即可。',
    copyFallback: '自动复制未成功，提示词已选中，请手动复制。',
    scenarios: {
      same: { title: '内容与确认时一致', draft: '版本 A', base: '原状态', draftNote: '与确认时一致', baseNote: '与试算时一致', outcome: 'pass', result: '可以保存', note: '摘要一致、必要检查通过后，正文与相关记录一起写入。' },
      draft: { title: '确认之后，候选稿又改了', draft: '版本 B', base: '原状态', draftNote: '已不是你确认的版本 A', baseNote: '与试算时一致', outcome: 'stop', result: '暂停保存：重新试算并确认', note: '新稿有新的内容摘要，之前的确认不适用于它。' },
      base: { title: '试算之后，正式文件变了', draft: '版本 A', base: '新状态', draftNote: '候选稿本身没有变化', baseNote: '相关的原文件已被修改', outcome: 'stop', result: '暂停保存：基于当前文件重新核对', note: '先处理文件变化，再重新试算并确认，避免依据过期的状态保存。' }
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
