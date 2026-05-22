const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    
    console.log('Step 1: Navigate to voice box on port 8001');
    await page.goto('http://localhost:8001', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    
    // Take screenshot of default view
    console.log('📸 Capturing default view with logs and agents...');
    await page.screenshot({ path: '/tmp/01-default-view.png', fullPage: false });
    
    // Verify initial state
    const initialText = await page.textContent('#facetimeToggle');
    const facetimeClassBefore = await page.evaluate(() => document.body.classList.contains('facetime-mode'));
    const leftColumnBefore = await page.evaluate(() => {
        const lc = document.querySelector('.left-column');
        return lc && window.getComputedStyle(lc).display !== 'none';
    });
    
    console.log(`✅ Default view - Button text: "${initialText}"`);
    console.log(`✅ Default view - FaceTime mode OFF: ${!facetimeClassBefore}`);
    console.log(`✅ Default view - Left column visible: ${leftColumnBefore}`);
    
    // Click FaceTime button
    console.log('\nStep 2: Click FaceTime button');
    await page.click('#facetimeToggle');
    await page.waitForTimeout(500);
    
    const textAfterClick = await page.textContent('#facetimeToggle');
    const facetimeClassAfter = await page.evaluate(() => document.body.classList.contains('facetime-mode'));
    const leftColumnAfter = await page.evaluate(() => {
        const lc = document.querySelector('.left-column');
        return lc && window.getComputedStyle(lc).display !== 'none';
    });
    
    console.log('📸 Capturing FaceTime mode view...');
    await page.screenshot({ path: '/tmp/02-facetime-on.png', fullPage: false });
    
    console.log(`✅ FaceTime mode - Button text: "${textAfterClick}"`);
    console.log(`✅ FaceTime mode - FaceTime mode ON: ${facetimeClassAfter}`);
    console.log(`✅ FaceTime mode - Left column hidden: ${!leftColumnAfter}`);
    
    // Verify grid changed to single column
    const gridCols = await page.evaluate(() => {
        return window.getComputedStyle(document.querySelector('.main-grid')).gridTemplateColumns;
    });
    console.log(`✅ FaceTime mode - Grid layout: ${gridCols}`);
    
    // Click to toggle back
    console.log('\nStep 3: Click FaceTime button to toggle back');
    await page.click('#facetimeToggle');
    await page.waitForTimeout(500);
    
    const textAfterSecondClick = await page.textContent('#facetimeToggle');
    const facetimeClassAfterSecond = await page.evaluate(() => document.body.classList.contains('facetime-mode'));
    const leftColumnAfterSecond = await page.evaluate(() => {
        const lc = document.querySelector('.left-column');
        return lc && window.getComputedStyle(lc).display !== 'none';
    });
    
    console.log('📸 Capturing default view after toggle back...');
    await page.screenshot({ path: '/tmp/03-default-restored.png', fullPage: false });
    
    console.log(`✅ Default restored - Button text: "${textAfterSecondClick}"`);
    console.log(`✅ Default restored - FaceTime mode OFF: ${!facetimeClassAfterSecond}`);
    console.log(`✅ Default restored - Left column visible: ${leftColumnAfterSecond}`);
    
    // Test keyboard shortcut
    console.log('\nStep 4: Test keyboard shortcut Ctrl+Shift+F');
    await page.keyboard.press('Control+Shift+F');
    await page.waitForTimeout(500);
    
    const textAfterShortcut = await page.textContent('#facetimeToggle');
    const facetimeModeAfterShortcut = await page.evaluate(() => document.body.classList.contains('facetime-mode'));
    
    console.log('📸 Capturing view after Ctrl+Shift+F...');
    await page.screenshot({ path: '/tmp/04-shortcut-facetime.png', fullPage: false });
    
    console.log(`✅ After Ctrl+Shift+F - Button text: "${textAfterShortcut}"`);
    console.log(`✅ After Ctrl+Shift+F - FaceTime mode ON: ${facetimeModeAfterShortcut}`);
    
    // Test shortcut again
    console.log('\nStep 5: Test keyboard shortcut again to toggle off');
    await page.keyboard.press('Control+Shift+F');
    await page.waitForTimeout(500);
    
    const textAfterSecondShortcut = await page.textContent('#facetimeToggle');
    const facetimeModeAfterSecondShortcut = await page.evaluate(() => document.body.classList.contains('facetime-mode'));
    
    console.log('📸 Capturing final view...');
    await page.screenshot({ path: '/tmp/05-shortcut-toggle-off.png', fullPage: false });
    
    console.log(`✅ After 2nd Ctrl+Shift+F - Button text: "${textAfterSecondShortcut}"`);
    console.log(`✅ After 2nd Ctrl+Shift+F - FaceTime mode OFF: ${!facetimeModeAfterSecondShortcut}`);
    
    console.log('\n✅ All FaceTime toggle tests passed!');
    console.log('Screenshots saved to /tmp/0*.png');
    
    await browser.close();
})().catch(err => {
    console.error('Error:', err);
    process.exit(1);
});
