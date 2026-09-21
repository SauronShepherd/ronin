import assert from 'node:assert/strict';
import {hasMessage, messageIds, pseudoLocale, pseudoT, t} from './i18n.js';

assert.equal(t('nav.home'), 'Overview');
assert.equal(hasMessage('nav.runs'), true);
assert.equal(hasMessage('nav.missing'), false);
assert.ok(messageIds().includes('nav.migration'));
assert.equal(pseudoLocale('Run {id}'), '[Rün {ïd}··]');
assert.equal(pseudoT('nav.home'), '[Õvërvïëw··]');
globalThis.__RONIN_PSEUDO_LOCALE__ = true;
assert.equal(t('nav.home'), '[Õvërvïëw··]');
delete globalThis.__RONIN_PSEUDO_LOCALE__;

globalThis.__RONIN_I18N_STRICT__ = true;
assert.throws(() => t('missing.message'), /Missing message/);
delete globalThis.__RONIN_I18N_STRICT__;

console.log(`i18n contract passed (${messageIds().length} messages)`);
