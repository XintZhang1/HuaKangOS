// 金额解析回归：把 web/app.js 的解析实现放入函数作用域执行（不依赖浏览器）
const fs=require('fs');
const src=fs.readFileSync('web/app.js','utf8');
const start=src.indexOf('const moneyDigits=');
const end=src.indexOf('const number=v=>');
if(start<0||end<0)throw new Error('money helper not found');
const moneyFen=new Function(src.slice(start,end)+'; return moneyFen;')();
const cases=[
 ['145,500.00',14550000],['80000',8000000],['80,000.00',8000000],['65.00',6500],
 ['1,234,567.89',123456789],['１４５，５００．００',14550000],['￥1,200.50',120050],
 ['0.00',0],[' 12.5 ',1250],['0',0],['１２３',12300],
 ['-5',null],['abc',null],['1.234',null],['',null],['1,2,3.456',null],
];
let bad=0;
for(const [input,expect] of cases){
 let got;try{got=moneyFen(input,{allowZero:true})}catch(e){got=null}
 if(got!==expect){bad++;console.log('MISMATCH',JSON.stringify(input),'got',got,'expect',expect)}
}
let zeroRejected=false;try{moneyFen('0',{label:'金额'})}catch(e){zeroRejected=true}
if(!zeroRejected){bad++;console.log('MISMATCH: 正数口径必须拒绝 0')}
let commaAccepted=false;try{commaAccepted=moneyFen('145,500.00',{label:'金额'})===14550000}catch(e){}
if(!commaAccepted){bad++;console.log('MISMATCH: 正数口径必须接受千分位默认值')}
console.log(bad===0?'moneyFen regression: PASS':`moneyFen regression: FAIL (${bad})`);
process.exit(bad===0?0:1);