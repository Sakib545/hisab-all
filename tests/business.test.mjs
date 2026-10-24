import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {parcelTotals,availableStock,parseReceipt} from '../lib/business.ts';
const product={id:'hair',stock:10};
const base={productId:'hair',quantity:2,unitCost:20000,salePrice:50000,packaging:3000,courierFee:8000,returnFee:5000,deliveryCharge:10000,otherCost:2000,collected:0};
test('delivery recognizes sales, snapshots and COD without counting drafts',()=>{const rows=[{...base,status:'delivered'},{...base,status:'draft'}];const t=parcelTotals(rows);assert.equal(t.revenue,110000);assert.equal(t.cogs,40000);assert.equal(t.totalCost,53000);assert.equal(t.profit,57000);assert.equal(t.codPending,110000);assert.equal(availableStock(product,rows),8)});
test('return restores stock, incurs packaging/courier/return fees, no sales or COGS',()=>{const rows=[{...base,status:'returned'}];const t=parcelTotals(rows);assert.equal(t.revenue,0);assert.equal(t.cogs,0);assert.equal(t.totalCost,18000);assert.equal(availableStock(product,rows),10)});
test('sent stock allocated, cancelled parcel excluded, collected COD clears pending',()=>{assert.equal(availableStock(product,[{...base,status:'sent'},{...base,status:'cancelled'}]),8);assert.equal(parcelTotals([{...base,status:'delivered',collected:1}]).codPending,0)});
test('receipt parser prioritizes grand total over subtotal and handles Bangla digits',()=>{assert.deepEqual(parseReceipt('Subtotal 1000\nGrand Total: BDT 1,250.00\nDate: 20/10/2026\nReference ID: ABC12345'),{amount:'1250',date:'2026-10-20',reference:'ABC12345'});assert.equal(parseReceipt('সর্বমোট টাকা: ১,২৫০.৫০').amount,'1250.5');assert.equal(parseReceipt('No amount here').amount,'')});
