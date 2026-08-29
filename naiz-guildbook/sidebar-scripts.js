(function() {
  var nav = document.getElementById('sidebar-nav');
  if (!nav) return;
  var parts = location.pathname.split('/');
  var inPages = parts[parts.length - 2] === 'pages';
  var pp = inPages ? '' : 'pages/';       /* prefix for sibling page links */
  var home = inPages ? '../scripts.html' : 'scripts.html';
  var rootRef = inPages ? '../' : '';     /* prefix for root-level assets */
  if (inPages) { document.write('<script src="' + rootRef + 'topnav.js"><\/script>'); }
  var other = inPages ? '../manual.html' : 'manual.html';
  nav.innerHTML = [
    '<a class="nav-item nav-home" href="' + rootRef + 'index.html">← 总目录</a>',
    '<div class="sidebar-section">游戏剧本</div>',
    '<a class="nav-item" href="' + pp + 'sc01-NB剧本概述.html">NB 剧本概述</a>',
    '<a class="nav-item" href="' + pp + 'sc02-bg.html">bg 背景切换</a>',
    '<a class="nav-item" href="' + pp + 'sc03-char.html">char 立绘操作与对话</a>',
    '<a class="nav-item" href="' + pp + 'sc04-scene.html">scene 场景跳转</a>',
    '<a class="nav-item" href="' + pp + 'sc05-saveload.html">savescene 存档</a>',
    '<a class="nav-item" href="' + pp + 'sc06-gallery.html">cgvmenu 鉴赏</a>',
    '<a class="nav-item" href="' + pp + 'sc07-mainmenu.html">mainmenu 主菜单</a>',
    '<a class="nav-item" href="' + pp + 'sc08-question.html">question 选择分支</a>',
    '<a class="nav-item" href="' + pp + 'sc09-var.html">var 变量操作</a>',
    '<a class="nav-item" href="' + pp + 'sc10-audio.html">bgm/sound/voice 音频</a>',
    '<a class="nav-item" href="' + pp + 'sc11-sceneconf.html">sceneconf 场景配置</a>',
    '<a class="nav-item" href="' + pp + 'sc12-host.html">host 系统旁白</a>',
    '<a class="nav-item" href="' + pp + 'sc13-startsetting.html">startsetting 启动设置</a>',
    '<a class="nav-item" href="' + pp + 'sc14-settingmenu.html">settingmenu 设置菜单</a>',
    '<a class="nav-item" href="' + pp + 'sc15-playanima.html">playanima 播放动画</a>',
    '<a class="nav-item" href="' + pp + 'sc16-waitanima.html">waitanima 等待动画</a>',
    '<a class="nav-item" href="' + pp + 'sc17-stopanima.html">stopanima 停止动画</a>',
    '<a class="nav-item" href="' + pp + 'sc18-delay.html">delay 剧本延时</a>',
    '<a class="nav-item nav-other" href="' + other + '">基本概念 →</a>',
  ].join('\n');

  var page = location.pathname.split('/').pop();
  if (!page || page === '') page = 'index.html';
  var links = nav.querySelectorAll('.nav-item');
  for (var i = 0; i < links.length; i++) {
    if (links[i].getAttribute('href').split('/').pop() === page) {
      links[i].classList.add('active');
      break;
    }
  }
})();
