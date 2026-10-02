/* 配色切换：白天 / 夜间 / 自动（跟随系统）
   全站唯一的脚本。放在 <head> 里同步执行，首屏绘制前先套用已保存的配色，
   避免先闪一下系统色；点击绑定等 DOM 就绪后再做。
   没有 JS 时页面退回「跟随系统」——CSS 里的媒体查询会接管。 */
(function () {
  var KEY = 'theme';
  var root = document.documentElement;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }   // file:// 等场景可能不可用
  }
  var saved = stored();
  if (saved) { root.setAttribute('data-theme', saved); }

  function wire() {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');

    function sync() {
      // 高亮反映「用户选了什么」，不是「现在长什么样」：
      // 没有显式选择时，选中的是「自动」——哪怕此刻显示的是深色，也不该把「夜间」点亮。
      var chosen = root.getAttribute('data-theme') || 'auto';
      Array.prototype.forEach.call(document.querySelectorAll('[data-theme-set]'), function (btn) {
        btn.setAttribute('aria-pressed', String(btn.getAttribute('data-theme-set') === chosen));
      });
    }
    function apply(mode) {
      if (mode === 'auto') { root.removeAttribute('data-theme'); }
      else { root.setAttribute('data-theme', mode); }
      try {
        if (mode === 'auto') { localStorage.removeItem(KEY); } else { localStorage.setItem(KEY, mode); }
      } catch (e) { /* 存不了就只当次生效，不报错 */ }
      sync();
    }

    var box = document.querySelector('.theme');
    if (box) {
      box.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-theme-set]');
        if (btn) { apply(btn.getAttribute('data-theme-set')); }
      });
    }
    var onChange = function () { sync(); };
    if (mq.addEventListener) { mq.addEventListener('change', onChange); } else { mq.addListener(onChange); }
    sync();
  }

  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', wire); }
  else { wire(); }
})();
