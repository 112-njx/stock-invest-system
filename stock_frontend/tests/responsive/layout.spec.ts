import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const routes = {
  '/': '.login-landing',
  '/login': '.login-landing',
  '/market': '.market-grid',
  '/market/detail': '.detail-body',
  '/stocks': '.stocks-page',
  '/heatmap': '.heatmap-page',
  '/stockdb': '.blueprint',
  '/stockdb/trends': '.blueprint--trends',
  '/ai': '.ai-shell',
  '/forecast': '.forecast-page',
  '/admin': '.admin-console',
  '/forgot-password': '.auth-card',
  '/reset-password': '.auth-card',
  '/verify-email': '.auth-card',
  '/terms': '.market-grid',
  '/privacy': '.market-grid',
  '/disclaimer': '.market-grid',
}

const stock = { code: '600519', name: '贵州茅台', market: 'SSE', data_date: 20260105, close: 1500, change_pct: 1.2, industry: '食品饮料' }
const heatStock = { ...stock, change: 1.2, totalMv: 1e10, deltaMv: 1e8, value: 1e8 }
const heatmap = {
  date: 20260105, count: 1,
  boards: [{ code: 'food', name: '食品饮料', change: 1.2, value: 1e8, up: 1, down: 0, children: [heatStock] }],
}

async function stubApi(page: Page, admin = () => false) {
  // Mock sockets as well as HTTP, so this suite never needs the local backend.
  await page.routeWebSocket('**/api/**', socket => { socket.onMessage(() => {}) })
  await page.route('**/api/**', route => {
    const { pathname } = new URL(route.request().url())
    if (pathname.endsWith('/auth/refresh')) return route.fulfill(admin()
      ? { json: { code: 0, data: { token: 'layout-fixture' } } }
      : { status: 401, json: { code: 401, msg: 'guest' } })
    if (pathname.endsWith('/users/me')) return route.fulfill({
      json: { code: 0, data: { id: 1, username: 'root', is_admin: true, email: 'root@example.test' } },
    })
    if (pathname.endsWith('/stockdb/equities')) return route.fulfill({
      json: { code: 0, data: { items: [stock], industries: [stock.industry], date: 20260105, loading: false } },
    })
    if (pathname.endsWith('/stockdb/heatmap')) return route.fulfill({ json: heatmap })
    if (pathname.endsWith('/stockdb/home')) return route.fulfill({
      json: { version: 'layout-fixture', charts: {}, boards: [], boardId: '' },
    })
    return route.fulfill({ status: 503, json: { code: 503, detail: 'Fixture unavailable' } })
  })
}

async function expectNoPageOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() =>
    Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) - document.documentElement.clientWidth,
  )).toBeLessThanOrEqual(1)
}

test('every router entry has a layout check', () => {
  test.skip(test.info().project.name !== 'desktop')
  const source = readFileSync(new URL('../../src/router/index.ts', import.meta.url), 'utf8')
  const declared = Array.from(source.matchAll(/\bpath:\s*['"]([^'"]+)['"]/g), match => match[1])
  expect(Object.keys(routes).sort()).toEqual(declared.sort())
})

test('every page fits the viewport', async ({ page, viewport }, info) => {
  test.setTimeout(120_000)
  let admin = false
  await stubApi(page, () => admin)
  for (const [path, visible] of Object.entries(routes)) {
    await test.step(path, async () => {
      admin = path === '/admin'
      await page.goto(path, { waitUntil: 'domcontentloaded' })
      await expect(page.locator(visible)).toBeVisible()
      await expectNoPageOverflow(page)
      if (path === '/market/detail') {
        const chart = await page.locator('.kline-chart__canvas').boundingBox()
        expect(chart?.width).toBeGreaterThan(info.project.name.startsWith('phone') ? viewport!.width * 0.8 : 300)
        expect(chart?.height).toBeGreaterThan(160)
      }
    })
  }
})

test('account page links focus the inline homepage login form', async ({ page }, info) => {
  test.skip(!['desktop', 'phone-390'].includes(info.project.name))
  await stubApi(page)
  for (const [path, label] of [
    ['/forgot-password', '返回登录'],
    ['/reset-password', '返回登录'],
    ['/verify-email', '前往登录'],
  ]) {
    await page.goto(path!)
    await page.getByRole('button', { name: label }).click()
    await expect(page).toHaveURL(/\/#sign-in$/)
    const form = page.getByRole('region', { name: '登录或注册' })
    await expect(form).toBeFocused()
    await expect(form.getByLabel('用户名')).toBeInViewport()
  }
})

test('forecast navigation opens a stock history preview', async ({ page }, info) => {
  if (!['desktop', 'phone-320', 'phone-landscape'].includes(info.project.name)) test.skip()
  await stubApi(page)
  await page.route('**/api/v1/stocks/search-directory', route => route.fulfill({ json: {
    code: 0, data: { version: 'forecast-fixture', source: 'stockdb', items: [
      { code: stock.code, name: stock.name, type: 'stock', market: stock.market, ordinal: 1, latest_date: '2026-01-05' },
    ] },
  } }))
  await page.route('**/api/v1/kline?*', route => {
    const params = new URL(route.request().url()).searchParams
    expect(params.get('symbol')).toBe(stock.code)
    expect(params.get('period')).toBe('1d')
    return route.fulfill({ json: { code: 0, data: [
      { ts: '2026-01-05T07:00:00Z', open: 1490, high: 1510, low: 1480, close: 1500, volume: 100, amount: 150000 },
    ] } })
  })
  await page.goto('/ai')
  if (info.project.name !== 'desktop') await page.getByRole('button', { name: '菜单', exact: true }).click()
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '预测走势' }).click()
  await expect(page).toHaveURL(/\/forecast$/)
  await page.getByRole('combobox', { name: '搜索股票名称、拼音或代码' }).fill(stock.code)
  await page.getByRole('option', { name: /600519/ }).click()
  await expect(page.getByRole('cell', { name: '1,500.00' })).toBeVisible()
  await expectNoPageOverflow(page)
})

test('forecast shows both stages and can enable tracking', async ({ page }, info) => {
  test.skip(!['desktop', 'phone-320', 'phone-landscape'].includes(info.project.name))
  await stubApi(page, () => true)
  const session = '2026-01-05'
  const evidence = [{ session, feature: 'ema20', value: 1500, reason: '收盘在均线上方' }]
  const run = {
    id: 42, symbol: stock.code, trigger: 'manual', status: 'predicting', created_at: `${session}T08:00:00Z`,
    snapshot: { latest_session: session, as_of: `${session}T16:00:00+08:00`, bar_count: 40,
      data_version: 'a'.repeat(64), feature_version: 1, source: 'stockdb' },
    diagnosis: { regime: 'tight_channel', bias: 'up', summary: '窄通道延续', evidence },
    models: { diagnosis: { name: 'test-model', revision: null } }, error: null,
  }
  let started = false
  let complete = false
  let tracking = false
  await page.route('**/api/v1/stocks/search-directory', route => route.fulfill({ json: {
    code: 0, data: { version: 'forecast-analysis-fixture', source: 'stockdb', items: [
      { code: stock.code, name: stock.name, type: 'stock', market: stock.market, ordinal: 1, latest_date: session },
    ] },
  } }))
  await page.route('**/api/v1/forecast/runs**', route => {
    if (route.request().method() === 'POST') {
      started = true
      return route.fulfill({ json: { code: 0, data: run } })
    }
    const result = complete ? {
      ...run, status: 'completed', prediction: {
        next_candle: { direction: 'up', reason: '收盘延续', evidence },
        next_regime: { regime: 'undetermined', reason: '后续信号冲突', evidence: [] },
      },
    } : run
    return route.fulfill({ json: { code: 0, data: { runs: started ? [result] : [], tracking } } })
  })
  await page.route('**/api/v1/forecast/tracking', route => {
    tracking = route.request().postDataJSON().enabled
    return route.fulfill({ json: { code: 0, data: { tracking } } })
  })
  await page.goto('/forecast')
  await page.getByRole('combobox', { name: '搜索股票名称、拼音或代码' }).fill(stock.code)
  await page.getByRole('option', { name: /600519/ }).click()
  await expect(page.getByRole('button', { name: '开启自动跟踪' })).toBeVisible()
  await page.getByRole('button', { name: '分析走势' }).click()
  await expect(page.getByText('第二阶段 · 正在推演走势')).toBeVisible()
  await expect(page.getByText('2026-01-05 · EMA20 1,500')).toBeVisible()
  complete = true
  await expect(page.getByRole('heading', { name: '下一根日 K 线 · 涨' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '下一阶段走势 · 无法判断' })).toBeVisible()
  await page.getByRole('button', { name: '开启自动跟踪' }).click()
  await expect(page.getByRole('button', { name: '关闭自动跟踪' })).toHaveAttribute('aria-pressed', 'true')
  await expectNoPageOverflow(page)
})

test('inline homepage login returns to the requested route', async ({ page }, info) => {
  test.skip(!['desktop', 'phone-390'].includes(info.project.name))
  await stubApi(page)
  await page.route('**/api/v1/auth/login', route => route.fulfill({
    json: { code: 0, data: { token: 'test-token', user: { id: 1, username: 'tester' } } },
  }))
  await page.goto('/?redirect=%2Fstocks')
  const form = page.getByRole('region', { name: '登录或注册' })
  await form.getByLabel('用户名').fill('tester')
  await form.getByLabel('密码', { exact: true }).fill('test-password')
  await form.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/stocks$/)
})

test('phone navigation, chart controls and dialog focus', async ({ page }, info) => {
  test.skip(!info.project.name.startsWith('phone'))
  await stubApi(page)
  await page.goto('/market')
  const menu = page.getByRole('button', { name: '菜单', exact: true })
  await menu.tap()
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '股票' }).tap()
  await expect(page).toHaveURL(/\/stocks$/)
  await expect(menu).toHaveAttribute('aria-expanded', 'false')
  const search = page.getByRole('button', { name: '搜索', exact: true })
  await search.tap()
  await expect(page.getByRole('combobox', { name: '搜索股票名称、拼音或代码' })).toBeVisible()
  await search.tap()
  const login = page.getByRole('button', { name: '登录 / 注册', exact: true })
  await login.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: '登录或注册' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '关闭', exact: true }).tap()
  await expect(dialog).toHaveCount(0)
  await expect(login).toBeFocused()
  await page.goto('/market')
  await page.getByRole('link', { name: '查看行情详情' }).tap()
  await page.getByTitle('选择技术指标').tap()
  await expect(page.locator('.modal--indicator-detail')).toBeVisible()
  await expectNoPageOverflow(page)
})

test('phone stock table preserves access to all columns and row actions', async ({ page }, info) => {
  test.skip(!info.project.name.startsWith('phone'))
  await stubApi(page)
  await page.goto('/stocks')
  await page.getByRole('button', { name: '贵州茅台的更多操作' }).tap()
  await expect(page.getByRole('menuitem', { name: '加入关注' })).toBeVisible()
  await page.getByRole('button', { name: '完整表格' }).tap()
  await expect(page.getByRole('button', { name: '精简表格' })).toBeVisible()
  expect(await page.locator('.table-wrap').evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
  await expectNoPageOverflow(page)
  await page.getByRole('button', { name: '精简表格' }).tap()
  await page.getByRole('row', { name: '600519 贵州茅台' }).locator('.name').tap()
  await expect(page).toHaveURL(/\/market\/detail\?symbol=600519/)
})

test('phone search hides the previous quote until the selected stock resolves', async ({ page }, info) => {
  test.skip(info.project.name !== 'phone-390')
  await stubApi(page)
  const next = { ...stock, code: '600520', name: '搜索标的', type: 'stock', latest_date: '2026-01-05', ordinal: 1 }
  let allowNextSymbol = false
  await page.route('**/api/v1/stocks/search-directory', route => route.fulfill({
    json: { code: 0, data: { version: 'review-test', latest_session: '2026-01-05', items: [next] } },
  }))
  await page.route('**/api/v1/symbols?*', route => {
    const search = new URL(route.request().url()).searchParams.get('search')
    const data = search === stock.code ? [{ ...stock, id: 41, type: 'stock' }]
      : search === next.code && allowNextSymbol ? [{ ...next, id: 42 }] : []
    return route.fulfill({ json: { code: 0, data } })
  })
  await page.goto('/market/detail?symbol=600519&asset_type=stock')
  await expect(page.locator('.detail-summary')).toContainText('贵州茅台')
  await page.getByRole('button', { name: '搜索', exact: true }).tap()
  await page.getByRole('combobox', { name: '搜索股票名称、拼音或代码' }).tap()
  await page.getByRole('option', { name: /搜索标的/ }).tap()
  await expect(page).toHaveURL(/symbol=600520/)
  await expect(page.getByRole('alert')).toHaveText('无法加载标的 600520 的行情。')
  await expect(page.locator('.detail-body')).toHaveCount(0)
  allowNextSymbol = true
  await page.getByRole('button', { name: '重试', exact: true }).tap()
  await expect(page.locator('.detail-summary')).toContainText('搜索标的 · 600520')
})

test('phone opens stock detail at the top and restores the list on back', async ({ page }, info) => {
  test.skip(info.project.name !== 'phone-landscape')
  await stubApi(page)
  await page.route('**/api/v1/symbols?*', route => route.fulfill({
    json: { code: 0, data: [{ ...stock, id: 41, type: 'stock' }] },
  }))
  await page.goto('/stocks')
  const nameCell = page.getByRole('row', { name: '600519 贵州茅台' }).locator('.name')
  await expect(nameCell).toBeVisible()
  await page.evaluate(() => scrollTo(0, 160))
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(160)
  await nameCell.tap()
  await expect(page.locator('.detail-summary')).toContainText('贵州茅台')
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0)
  await page.goBack()
  await expect(nameCell).toBeVisible()
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(160)
})

test('stopping a stream keeps the partial response in the chat', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop')
  await stubApi(page, () => true)
  for (const endpoint of ['conversations', 'strategies', 'agents']) {
    await page.route(new RegExp('/api/v1/' + endpoint + '(?:\\?|$)'), route => route.fulfill({
      json: { code: 0, data: route.request().method() === 'POST' ? { id: 1, title: '测试' } : { items: [], total: 0 } },
    }))
  }
  await page.addInitScript(() => {
    const fetchFromNetwork = window.fetch.bind(window)
    window.fetch = (input, init) => {
      if (input !== '/api/v1/chat') return fetchFromNetwork(input, init)
      return Promise.resolve(new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode('data: {"type":"delta","seq":1,"content":"已收到的回复"}\n\n'))
          init?.signal?.addEventListener('abort', () => controller.error(init.signal!.reason), { once: true })
        },
      }), { headers: { 'Content-Type': 'text/event-stream' } }))
    }
  })
  await page.goto('/ai')
  await page.locator('.ci-textarea').fill('测试主动停止')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByText('已收到的回复', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '停止', exact: true }).click()
  await expect(page.getByText('已收到的回复', { exact: true })).toHaveCount(1)
  await expect(page.getByText('已停止生成', { exact: true })).toBeVisible()
})

test('desktop header focus still lets Escape close notifications and leave detail', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop')
  await stubApi(page, () => true)
  await page.goto('/market/detail')
  await page.getByTitle('通知', { exact: true }).click()
  const notifications = page.getByRole('dialog', { name: '通知中心' })
  await expect(notifications).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(notifications).toHaveCount(0)
  await expect(page).toHaveURL(/\/market\/detail$/)
  await page.getByTitle(/切换到.*模式/).focus()
  await page.keyboard.press('Escape')
  await expect(page).toHaveURL(/\/market$/)
})

test('phone heatmap shows details on tap', async ({ page }, info) => {
  test.skip(!info.project.name.startsWith('phone'))
  await stubApi(page)
  await page.goto('/heatmap')
  await expect(page.getByRole('option', { name: '食品饮料' })).toHaveCount(1)
  await expect(page.getByText('正在读取本地收盘行情…')).toHaveCount(0)
  await page.locator('.map canvas').tap()
  await expect(page.getByRole('region', { name: '云图股票详情' })).toContainText('贵州茅台')
  await page.getByRole('button', { name: '放大该行业' }).tap()
  await expect(page.getByRole('combobox', { name: '选择行业' })).toHaveValue('food')
})

test('phone AI session drawer returns to the chat input', async ({ page }, info) => {
  test.skip(!info.project.name.startsWith('phone'))
  await stubApi(page)
  await page.goto('/ai')
  await page.getByRole('button', { name: '会话与策略', exact: true }).tap()
  const drawer = page.getByRole('dialog', { name: '会话与策略' })
  await expect(drawer.getByRole('button', { name: '聊天', exact: true })).toBeVisible()
  await drawer.getByRole('button', { name: '关闭会话与策略' }).tap()
  await page.getByRole('button', { name: '会话与策略', exact: true }).tap()
  await drawer.locator('.j-menu__item').first().tap()
  await expect(drawer).toHaveCount(0)
  const login = page.getByRole('dialog', { name: '登录或注册' })
  await login.getByLabel('用户名').tap()
  await expect(login.getByLabel('用户名')).toBeFocused()
  await login.getByRole('button', { name: '关闭', exact: true }).tap()

  await page.locator('.symbol-picker__trigger').tap()
  const picker = page.locator('.symbol-picker__panel')
  await expect(picker).toBeVisible()
  const bounds = (await picker.boundingBox())!
  const main = page.locator('.ai-main')
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  expect(await main.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
  await page.locator('.symbol-picker__trigger').tap()
  await page.locator('.ci-textarea').fill('布局回归检查')
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled()
  await expectNoPageOverflow(page)
})

test('desktop retains its columns and mouse shortcuts', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop')
  await stubApi(page)
  await page.goto('/market/detail')
  const chart = (await page.locator('.col-left').boundingBox())!
  const sidebar = (await page.locator('.col-right').boundingBox())!
  expect(sidebar.x).toBeGreaterThanOrEqual(chart.x + chart.width)
  await expect(page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '股票' })).toBeVisible()
  await page.goto('/stocks')
  const row = page.getByRole('row', { name: '600519 贵州茅台' })
  await row.click({ button: 'right' })
  await expect(page.getByRole('menuitem', { name: '加入关注' })).toBeVisible()
  await page.keyboard.press('Escape')
  await row.locator('.name').dblclick()
  await expect(page).toHaveURL(/\/market\/detail\?symbol=600519/)
})
