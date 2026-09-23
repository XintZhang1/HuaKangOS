'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const source=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const start=source.indexOf('const time='),end=source.indexOf('\nconst heading=',start);
assert(start>=0&&end>start,'Load the actual application formatter');
const formatter=source.slice(start,end);
const intake=fs.readFileSync(path.join(root,'web/serviceintake.js'),'utf8').match(/^function intakeLocal\(value\).*$/m)?.[0];
assert(intake,'Load the unchanged local appointment input formatter');
const timestamps=['2026-09-23T07:17:00','2026-09-23T07:17:00.123456','2026-09-23T07:17:00Z','2026-09-23T07:17:00.123456+00:00','2026-09-23T15:17:00+08:00','2026-09-23T03:17:00-04:00','2026-09-23T07:17'];
const invalid=[null,undefined,'',false,0,1,{},[],'not a timestamp','2026/9/23 07:17','2026-09-23 07:17:00','2026-02-29','2026-04-31','0000-01-01','2026-13-01','2026-00-01','2026-09-00','2026-09-23T24:00:00','2026-09-23T07:60:00Z','2026-09-23T07:17:60Z','2026-09-23T07:17:00+24:00','2026-09-23T07:17:00+08:60'];
const expectedUtc={'Asia/Shanghai':'2026-09-23T07:17:00.000Z','UTC':'2026-09-23T15:17:00.000Z','America/New_York':'2026-09-23T19:17:00.000Z'};
for(const zone of Object.keys(expectedUtc)){
 const program=formatter+'\n'+intake+'\n'+`const timestamps=${JSON.stringify(timestamps)},invalid=${JSON.stringify(invalid)};console.log(JSON.stringify({zone:Intl.DateTimeFormat().resolvedOptions().timeZone,timestamps:timestamps.map(time),dates:['2026-09-23','2024-02-29'].map(time),invalid:invalid.map(time),missing:time(undefined),dateObject:time(new Date()),rollover:time('2026-09-23T23:59:59.999999'),midnight:time('2026-09-23T16:00:00Z'),localApi:new Date('2026-09-23T15:17').toISOString(),localRoundtrip:intakeLocal(new Date('2026-09-23T15:17').toISOString())}));`;
 const actual=JSON.parse(execFileSync(process.execPath,['-e',program],{encoding:'utf8',env:{...process.env,TZ:zone},timeout:15000,windowsHide:true}));
 test(zone+': UTC-naive, Z and explicit offsets show the same Shanghai event time',()=>{
  assert.equal(actual.zone,zone);assert.deepEqual(actual.timestamps,timestamps.map(()=>'2026/9/23 15:17:00'));
  assert.equal(actual.rollover,'2026/9/24 07:59:59');assert.equal(actual.midnight,'2026/9/24 00:00:00');
 });
 test(zone+': calendar dates stay dates and invalid/ambiguous values are empty',()=>{
  assert.deepEqual(actual.dates,['2026-09-23','2024-02-29']);assert.deepEqual(actual.invalid,invalid.map(()=>'—'));
  assert.equal(actual.missing,'—');assert.equal(actual.dateObject,'—');
 });
 test(zone+': appointment local input conversion remains separate and unchanged',()=>{
  assert.equal(actual.localApi,expectedUtc[zone]);assert.equal(actual.localRoundtrip,'2026-09-23T15:17');
 });
}
