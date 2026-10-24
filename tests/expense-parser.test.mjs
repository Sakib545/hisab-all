import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {parseExpenses,parseAmountOnly,weekRange,monthRange,categoryTotals} from '../lib/expense-parser.ts';
test('same results as the bot parser',()=>{
  assert.deepEqual(parseExpenses('10000 তেলের টাকা'),[{amount:10000,category:'তেলের টাকা'}]);
  assert.deepEqual(parseExpenses('৳১০,৫০০ নারিকেল তেলের টাকা'),[{amount:10500,category:'নারিকেল তেলের টাকা'}]);
  assert.deepEqual(parseExpenses('500 খাবার'),[{amount:500,category:'খাবার'}]);
  assert.deepEqual(parseExpenses('500 খরচ 300 খাবার'),[{amount:500,category:'খরচ'},{amount:300,category:'খাবার'}]);
  assert.deepEqual(parseExpenses('500 খরচ\n300 খাবার'),[{amount:500,category:'খরচ'},{amount:300,category:'খাবার'}]);
  assert.deepEqual(parseExpenses('0 বেতন'),[]);
  assert.deepEqual(parseExpenses('আজকে 500 খাবার'),[]);
  assert.deepEqual(parseExpenses('500 123'),[]);
});
test('amount only',()=>{assert.equal(parseAmountOnly('৳১,২০০'),1200);assert.equal(parseAmountOnly('500 খাবার'),null);assert.equal(parseAmountOnly('0'),null)});
test('week (Mon–Sun) and month ranges',()=>{assert.deepEqual(weekRange(0,'2026-10-20'),['2026-10-19','2026-10-25']);assert.deepEqual(weekRange(1,'2026-10-19'),['2026-10-12','2026-10-18']);assert.deepEqual(monthRange(0,'2026-10-20'),['2026-10-01','2026-10-31']);assert.deepEqual(monthRange(10,'2026-10-20'),['2025-12-01','2025-12-31'])});
test('category totals order',()=>{assert.deepEqual(categoryTotals([{category:'খাবার',amount:1},{category:'বেতন',amount:5},{category:'তেলের টাকা',amount:2},{category:'বেতন',amount:5}]).map(r=>[r.category,r.amount]),[['তেলের টাকা',2],['বেতন',10],['খাবার',1]])});
