import assert from 'node:assert/strict';
import {createStudioContext, decodeStudioContext, encodeStudioContext} from './studio-context.js';

const context = createStudioContext({project: 'demo', revision: 'r/1', runtime: 'local', secret: 'ignored'});
assert.deepEqual(context, {project: 'demo', revision: 'r/1', runtime: 'local'});
assert.equal(Object.isFrozen(context), true);

const encoded = encodeStudioContext({project: 'demo', run: 'run/1'});
assert.equal(encoded, 'project=demo&run=run%2F1');
assert.deepEqual(decodeStudioContext(encoded), {project: 'demo', run: 'run/1'});

assert.throws(() => createStudioContext({project: '\u0000'}), /bounded/);
assert.throws(() => createStudioContext({project: 'x'.repeat(257)}), /bounded/);

console.log('studio context contract passed');
