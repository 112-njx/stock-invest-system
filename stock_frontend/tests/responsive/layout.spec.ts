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
