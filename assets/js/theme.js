/* 配色切换：报头一个图标按钮，点击循环 自动 → 白天 → 夜间 → 自动
   全站唯一的脚本。放在 <head> 里同步执行，首屏绘制前先套用已保存的配色，
   避免先闪一下系统色；点击绑定等 DOM 就绪后再做。

   分工：显示哪个图标由 CSS 依据 <html> 上的状态决定（没有属性 = 自动），
   脚本不参与渲染——即使脚本没跑起来，图标也不会和实际配色对不上。
   脚本只做两件事：记住选择、把「当前状态 + 下一次会切成什么」写进无障碍名称。
   没有 JS 时页面退回「跟随系统」，图标就是那个半明半暗的圆。 */
(function () {
  var KEY = 'theme';
  var root = document.documentElement;
  var ORDER = { auto: 'light', light: 'dark', dark: 'auto' };      // 点击顺序
  var NAME = { auto: '自动（跟随系统）', light: '白天', dark: '夜间' };
  var VALID = { light: 1, dark: 1 };

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }   // file:// 等场景可能不可用
  }
  var saved = stored();
  if (VALID[saved]) { root.setAttribute('data-theme', saved); }

  function chosen() {                       // 用户选了什么（不是此刻显示什么）
    var now = root.getAttribute('data-theme');
    return VALID[now] ? now : 'auto';
  }

  function wire() {
    var btn = document.querySelector('.theme-btn');

    // 属性被外部写坏成非法值时，图标会因为 CSS 匹配不到而消失；这里顺手纠正
    if (root.hasAttribute('data-theme') && !VALID[root.getAttribute('data-theme')]) {
      root.removeAttribute('data-theme');
    }

    function relabel() {
      if (!btn) { return; }
      var now = chosen();
      var text = '配色：' + NAME[now] + '（点击切换为' + NAME[ORDER[now]] + '）';
      btn.setAttribute('aria-label', text);
      btn.setAttribute('title', text);
    }

    function apply(mode) {
      if (mode === 'auto') { root.removeAttribute('data-theme'); }
      else { root.setAttribute('data-theme', mode); }
      try {
        if (mode === 'auto') { localStorage.removeItem(KEY); } else { localStorage.setItem(KEY, mode); }
      } catch (e) { /* 存不了就只当次生效，不报错 */ }
      relabel();
    }

    if (btn) {
      btn.addEventListener('click', function () { apply(ORDER[chosen()]); });
      relabel();
    }
  }

  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', wire); }
  else { wire(); }
})();
