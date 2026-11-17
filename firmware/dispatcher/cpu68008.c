// SPDX-License-Identifier: Apache-2.0
// Original portable 68008 interpreter. Exceptions/prefetch are later milestones.
#include <stdbool.h>
#include "cpu68008.h"

typedef struct {cpu68008 *c;cpu_read8 read;cpu_write8 write;void *ctx;int status;} execution;
typedef struct {unsigned mode,reg,size,fc;uint32_t address,value;} operand;
static uint32_t mask(unsigned size) {return size==4 ? UINT32_MAX : (1u<<(size*8))-1;}
static uint32_t program_fc(cpu68008 *c) {return c->sr&0x2000 ? 6 : 2;}
static uint32_t data_fc(cpu68008 *c) {return c->sr&0x2000 ? 5 : 1;}
static void fail(execution *e,uint32_t fault) {e->c->state=CPU_FAILED;e->c->fault=fault;}
static void bus_failure(execution *e,int status) {
    e->status=status;
    if(status==CPU_BUS_BERR && e->c->state==CPU_RESET_VECTOR) {
        e->c->state=CPU_HALTED;e->c->halt_asserted=1;e->c->fault=CPU_FAULT_BUS;
    } else if(status==CPU_BUS_RESET)e->c->state=CPU_WAIT_RESET;
    else fail(e,CPU_FAULT_BUS);
}
static bool good(execution *e) {return !e->status && (e->c->state==CPU_RUNNING || e->c->state==CPU_RESET_VECTOR);}
static bool aligned(execution *e,uint32_t address,unsigned size) {
    if(size>1 && (address&1)) {e->c->address=address&0xfffff;fail(e,CPU_FAULT_ALIGNMENT);return false;}
    return true;
}
static uint32_t read_memory(execution *e,uint32_t address,unsigned size,uint32_t fc) {
    uint32_t value=0;
    if(!aligned(e,address,size))return 0;
    for(unsigned i=0;i<size && good(e);++i) {
        uint8_t byte=0;e->c->address=(address+i)&0xfffff;e->c->fc=fc;
        int status=e->read(e->ctx,e->c->address,fc,&byte);
        if(status) {bus_failure(e,status);break;}
        ++e->c->reads;value=(value<<8)|byte;
    }
    return value;
}
static void write_memory(execution *e,uint32_t address,unsigned size,uint32_t fc,uint32_t value,bool predec) {
    if(!aligned(e,address,size))return;
    if(!e->write) {fail(e,CPU_FAULT_OPCODE);return;}
    for(unsigned i=0;i<size && good(e);++i) {
        // 68000/008 long predecrement writes put the low word on the bus first.
        unsigned at=predec && size==4 ? (i^2) : i;
        e->c->address=(address+at)&0xfffff;e->c->fc=fc;
        int status=e->write(e->ctx,e->c->address,fc,(value>>((size-1-at)*8))&255);
        if(status) {bus_failure(e,status);break;}
        ++e->c->writes;
    }
}
static uint32_t fetch(execution *e,unsigned size) {
    uint32_t value=read_memory(e,e->c->pc,size,program_fc(e->c));
    if(good(e))e->c->pc+=size;
    return value;
}
static void set_a(cpu68008 *c,unsigned reg,uint32_t value) {
    c->a[reg]=value;
    if(reg==7) {if(c->sr&0x2000)c->ssp=value;else c->usp=value;}
}
static bool valid_ea(unsigned mode,unsigned reg,unsigned size,bool alterable,bool address_register,bool immediate) {
    if(mode==1)return address_register && size!=1;
    if(mode<7)return true;
    return reg<2 || (!alterable && (reg<4 || (reg==4 && immediate)));
}
static uint32_t indexed(execution *e,uint32_t base) {
    uint32_t ext=fetch(e,2),index=(ext&0x8000) ? e->c->a[(ext>>12)&7] : e->c->d[(ext>>12)&7];
    if(!(ext&0x800))index=(uint32_t)(int32_t)(int16_t)index;
    // 68000/008 brief format: bits 10..8 do not enable 68020 scaling/full EA.
    return base+index+(int32_t)(int8_t)ext;
}
static operand decode(execution *e,unsigned mode,unsigned reg,unsigned size) {
    operand o={.mode=mode,.reg=reg,.size=size,.fc=data_fc(e->c)};
    unsigned increment=size==1 && reg==7 ? 2 : size;
    switch(mode) {
    case 0:case 1:break;
    case 2:case 3:o.address=e->c->a[reg];break;
    case 4:set_a(e->c,reg,e->c->a[reg]-increment);o.address=e->c->a[reg];break;
    case 5:o.address=e->c->a[reg]+(int32_t)(int16_t)fetch(e,2);break;
    case 6:o.address=indexed(e,e->c->a[reg]);break;
    case 7:
        if(reg==0)o.address=(uint32_t)(int32_t)(int16_t)fetch(e,2);
        else if(reg==1)o.address=fetch(e,4);
        else if(reg==2) {uint32_t base=e->c->pc;o.address=base+(int32_t)(int16_t)fetch(e,2);o.fc=program_fc(e->c);}
        else if(reg==3) {o.address=indexed(e,e->c->pc);o.fc=program_fc(e->c);}
        else o.value=fetch(e,size==4 ? 4 : 2)&mask(size);
        break;
    }
    return o;
}
static uint32_t read_operand(execution *e,operand *o) {
    if(!good(e))return 0;
    if(o->mode==0)return e->c->d[o->reg]&mask(o->size);
    if(o->mode==1)return e->c->a[o->reg]&mask(o->size);
    if(o->mode==7 && o->reg==4)return o->value;
    return read_memory(e,o->address,o->size,o->fc);
}
static void postincrement(execution *e,operand *o) {
    if(good(e) && o->mode==3)set_a(e->c,o->reg,e->c->a[o->reg]+(o->size==1 && o->reg==7 ? 2 : o->size));
}
static void write_operand(execution *e,operand *o,uint32_t value) {
    if(!good(e))return;
    if(o->mode==0)e->c->d[o->reg]=(e->c->d[o->reg]&~mask(o->size))|(value&mask(o->size));
    else if(o->mode==1)set_a(e->c,o->reg,o->size==2 ? (uint32_t)(int32_t)(int16_t)value : value);
    else write_memory(e,o->address,o->size,o->fc,value,o->mode==4);
}
static void logical_flags(cpu68008 *c,uint32_t value,unsigned size) {
    value&=mask(size);c->sr&=~15u;
    if(!value)c->sr|=4;
    if(value&(1u<<(size*8-1)))c->sr|=8;
}
static void arithmetic_flags(cpu68008 *c,uint32_t dst,uint32_t src,uint32_t result,unsigned size,bool sub) {
    uint32_t limit=mask(size),sign=1u<<(size*8-1);
    dst&=limit;src&=limit;result&=limit;
    bool carry=sub ? src>dst : (uint64_t)dst+src>limit;
    bool overflow=((sub ? dst^src : ~(dst^src))&(dst^result)&sign)!=0;
    c->sr=(c->sr&~31u)|(carry ? 17 : 0)|(overflow ? 2 : 0)|(!result ? 4 : 0)|((result&sign) ? 8 : 0);
}
static bool condition(unsigned cc,uint32_t sr) {
    bool c=sr&1,v=sr&2,z=sr&4,n=sr&8;
    switch(cc) {
    case 0:return true;case 1:return false;case 2:return !c && !z;case 3:return c || z;
    case 4:return !c;case 5:return c;case 6:return !z;case 7:return z;
    case 8:return !v;case 9:return v;case 10:return !n;case 11:return n;
    case 12:return n==v;case 13:return n!=v;case 14:return !z && n==v;default:return z || n!=v;
    }
}
void cpu68008_init(cpu68008 *c) {*c=(cpu68008){.version=2,.state=CPU_WAIT_RESET};}
int cpu68008_reset(cpu68008 *c,cpu_read8 read,void *ctx) {
    c->state=CPU_RESET_VECTOR;c->sr=0x2700;c->fault=0;c->halt_asserted=0;
    c->opcode=0;c->instructions=0;c->reads=0;c->writes=0;++c->resets;
    execution e={c,read,0,ctx,0};
    c->ssp=read_memory(&e,0,4,6);
    if(good(&e)) {set_a(c,7,c->ssp);c->pc=read_memory(&e,4,4,6);}
    if(good(&e) && aligned(&e,c->pc,2))c->state=CPU_RUNNING;
    return e.status;
}
int cpu68008_execute(cpu68008 *c,cpu_read8 read,cpu_write8 write,void *ctx) {
    if(c->state!=CPU_RUNNING)return CPU_BUS_OK;
    execution e={c,read,write,ctx,0};c->instruction_pc=c->pc;
    uint32_t op=fetch(&e,2);c->opcode=op;
    if(!good(&e))return e.status;
    unsigned mode=(op>>3)&7,reg=op&7;
    if(op==0x4e71) { /* NOP */ }
    else if(op==0x4e72) {
        uint32_t sr=fetch(&e,2);
        if(good(&e)) {
            if(!(c->sr&0x2000) || (sr&0xe000)!=0x2000)fail(&e,CPU_FAULT_SR);
            else {c->sr=sr&0xa71f;c->state=CPU_STOPPED;}
        }
    } else if((op&0xff00)==0x4200) { // CLR: data alterable, including required read-before-write.
        unsigned size_code=(op>>6)&3,size=1u<<size_code;
        if(size_code==3 || !valid_ea(mode,reg,size,true,false,false))fail(&e,CPU_FAULT_OPCODE);
        else {
            operand o=decode(&e,mode,reg,size);
            if(mode!=0)(void)read_operand(&e,&o);
            write_operand(&e,&o,0);postincrement(&e,&o);
            if(good(&e))logical_flags(c,0,size);
        }
    } else if((op>>12)>=1 && (op>>12)<=3) { // MOVE.B/L/W and MOVEA.W/L.
        unsigned size=(op>>12)==1 ? 1 : (op>>12)==2 ? 4 : 2;
        unsigned dm=(op>>6)&7,dr=(op>>9)&7;
        if(!valid_ea(mode,reg,size,false,true,true) || !valid_ea(dm,dr,size,true,true,false))fail(&e,CPU_FAULT_OPCODE);
        else {
            operand source=decode(&e,mode,reg,size);
            uint32_t value=read_operand(&e,&source);postincrement(&e,&source);
            if(good(&e)) {
                operand destination=decode(&e,dm,dr,size);
                write_operand(&e,&destination,value);postincrement(&e,&destination);
                if(good(&e) && dm!=1)logical_flags(c,value,size);
            }
        }
    } else if((op&0xffc0)==0x0800 || (op&0xf1c0)==0x0100) { // BTST static/dynamic.
        bool dynamic=(op&0x100)!=0;
        unsigned size=mode==0 ? 4 : 1;
        if(!valid_ea(mode,reg,size,false,false,dynamic))fail(&e,CPU_FAULT_OPCODE);
        else {
            uint32_t bit=dynamic ? c->d[(op>>9)&7] : fetch(&e,2)&255;
            operand o=decode(&e,mode,reg,size);uint32_t value=read_operand(&e,&o);
            postincrement(&e,&o);
            if(good(&e))c->sr=(c->sr&~4u)|((value&(1u<<(bit&(size==4 ? 31 : 7)))) ? 0 : 4);
        }
    } else if((op&0xf0f8)==0x50c8) { // DBcc: word counter, flags unchanged.
        uint32_t base=c->pc;int32_t displacement=(int16_t)fetch(&e,2);
        if(good(&e) && !condition((op>>8)&15,c->sr)) {
            uint32_t counter=(c->d[reg]-1)&0xffff;
            c->d[reg]=(c->d[reg]&0xffff0000)|counter;
            if(counter!=0xffff && aligned(&e,base+displacement,2))c->pc=base+displacement;
        }
    } else if((op&0xf000)==0x5000 && (op&0xc0)!=0xc0) { // ADDQ/SUBQ.
        unsigned size=1u<<((op>>6)&3),amount=(op>>9)&7;
        if(!amount)amount=8;
        if(!valid_ea(mode,reg,size,true,true,false))fail(&e,CPU_FAULT_OPCODE);
        else {
            bool sub=(op&0x100)!=0;
            operand o=decode(&e,mode,reg,mode==1 ? 4 : size);
            uint32_t before=read_operand(&e,&o),result=sub ? before-amount : before+amount;
            write_operand(&e,&o,result);postincrement(&e,&o);
            if(good(&e) && mode!=1)arithmetic_flags(c,before,amount,result,size,sub);
        }
    } else if((op&0xff00)==0x0200) { // ANDI, including CCR and supervisor SR forms.
        unsigned code=(op>>6)&3,size=1u<<code;
        if(op==0x023c || op==0x027c) {
            if(op==0x027c && !(c->sr&0x2000))fail(&e,CPU_FAULT_SR);
            else {
                uint32_t value=fetch(&e,2);
                if(good(&e)) {
                    if(op==0x023c)c->sr=(c->sr&~31u)|(c->sr&value&31);
                    else {
                        uint32_t sr=c->sr&value&0xa71f;
                        if(!(sr&0x2000)) {c->ssp=c->a[7];c->a[7]=c->usp;}
                        c->sr=sr;
                    }
                }
            }
        } else if(code==3 || !valid_ea(mode,reg,size,true,false,false))fail(&e,CPU_FAULT_OPCODE);
        else {
            uint32_t immediate=fetch(&e,size==4 ? 4 : 2)&mask(size);
            operand o=decode(&e,mode,reg,size);uint32_t value=read_operand(&e,&o)&immediate;
            write_operand(&e,&o,value);postincrement(&e,&o);
            if(good(&e))logical_flags(c,value,size);
        }
    } else if((op&0xf0c0)==0x90c0) { // SUBA.W/L: word source sign extends; no flags.
        unsigned size=(op&0x100) ? 4 : 2;
        if(!valid_ea(mode,reg,size,false,true,true))fail(&e,CPU_FAULT_OPCODE);
        else {
            operand o=decode(&e,mode,reg,size);uint32_t value=read_operand(&e,&o);
            postincrement(&e,&o);
            if(size==2)value=(uint32_t)(int32_t)(int16_t)value;
            if(good(&e))set_a(c,(op>>9)&7,c->a[(op>>9)&7]-value);
        }
    } else if(((op&0xf018)==0xe008 && (op&0xc0)!=0xc0) || (op&0xfec0)==0xe2c0) { // LSR/LSL.
        bool memory=(op&0xc0)==0xc0,left=(op&0x100)!=0;
        unsigned size=memory ? 2 : 1u<<((op>>6)&3),count;
        if(memory)count=1;
        else if(op&0x20)count=c->d[(op>>9)&7]&63;
        else {count=(op>>9)&7;if(!count)count=8;}
        if(memory && (mode<2 || !valid_ea(mode,reg,size,true,false,false)))fail(&e,CPU_FAULT_OPCODE);
        else {
            operand o=decode(&e,memory ? mode : 0,reg,size);
            uint32_t value=read_operand(&e,&o),carry=0,sign=1u<<(size*8-1);
            for(unsigned i=0;i<count;++i) {
                carry=left ? (value&sign)!=0 : value&1;
                value=left ? (value<<1)&mask(size) : value>>1;
            }
            write_operand(&e,&o,value);postincrement(&e,&o);
            if(good(&e)) {
                logical_flags(c,value,size);c->sr|=carry;
                if(count)c->sr=(c->sr&~16u)|(carry<<4);
            }
        }
    } else if((op&0xf000)==0x6000) { // BRA, BSR, all fourteen Bcc conditions.
        uint32_t base=c->pc;
        int32_t displacement=(int8_t)op;
        if(!(op&255))displacement=(int16_t)fetch(&e,2);
        unsigned cc=(op>>8)&15;
        if(good(&e) && (cc==1 || condition(cc,c->sr))) {
            uint32_t target=base+displacement;
            if(aligned(&e,target,2)) {
                if(cc==1) {set_a(c,7,c->a[7]-4);write_memory(&e,c->a[7],4,data_fc(c),c->pc,true);}
                if(good(&e))c->pc=target;
            }
        }
    } else if((op&0xffc0)==0x4ec0) { // JMP: all 68000 control addressing modes.
        if(!(mode==2 || mode==5 || mode==6 || (mode==7 && reg<4)))fail(&e,CPU_FAULT_OPCODE);
        else {operand o=decode(&e,mode,reg,4);if(good(&e) && aligned(&e,o.address,2))c->pc=o.address;}
    } else fail(&e,CPU_FAULT_OPCODE);
    if(!e.status && (c->state==CPU_RUNNING || c->state==CPU_STOPPED))++c->instructions;
    return e.status;
}
int cpu68008_step(cpu68008 *c,cpu_read8 read,void *ctx) {return cpu68008_execute(c,read,0,ctx);}
