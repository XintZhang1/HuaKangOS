/* Presentation only. The same public group image is used on login and homepages.
   Keep the complete collage visible; its logos and slogan must not be cropped. */
function huakangLogo(){return '<svg class="hk-logo" viewBox="8 774 1304 1320" role="img" aria-label="华慷集团标志"><image href="/static/assets/huakang-logo-source.png" width="1320" height="2868"/></svg>';}
function huakangBrand(){return `<div class="brand hk-brand">${huakangLogo()}<span class="brandname">华慷集团<small class="brandgroup">huakangos</small></span></div>`;}
function huakangLogin(){return `<div class="loginpage hk-login"><section class="loginart"><img class="hk-login-photo" src="/api/branding/photo" alt="华慷集团品牌图：敬业、激情、包容、分享"></section><section class="hk-login-side"><div class="loginform"><div class="hk-login-form-brand">${huakangBrand()}</div><h2>登录</h2><form><label>账号<input name="username" autocomplete="username" required maxlength="40" placeholder="请输入账号"></label><label>密码<input name="password" type="password" autocomplete="current-password" required maxlength="128" placeholder="请输入密码"></label><div class="formerror" role="alert"></div><button type="submit" class="primary">登录<span aria-hidden="true">→</span></button></form></div><p class="hk-login-footer">华慷集团 · huakangos</p></section></div>`;}
function huakangPageHeading(title,subtitle,buttons='',type='work'){
 return `<section class="hk-page-hero hk-hero-${type}"><div class="hk-hero-content">${heading(title,subtitle,buttons)}</div><img class="hk-hero-photo" src="/api/branding/photo" alt="华慷集团品牌图：敬业、激情、包容、分享"></section>`;
}
