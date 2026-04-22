// Gate-level 4-bit ALU (simplified)
// Operations: AND, OR, XOR, ADD (ripple-carry)
// op[1:0]: 00=AND, 01=OR, 10=XOR, 11=ADD
// Flattened single-bit operations for parseability
module alu_4bit (a0,a1,a2,a3, b0,b1,b2,b3, op0,op1,
                 r0,r1,r2,r3, carry_out);
    input  a0,a1,a2,a3, b0,b1,b2,b3, op0,op1;
    output r0,r1,r2,r3, carry_out;

    // Internal wires
    wire and0,and1,and2,and3;
    wire or0, or1, or2, or3;
    wire xor0,xor1,xor2,xor3;
    wire sum0,sum1,sum2,sum3;
    wire c0,c1,c2;
    wire sel_and, sel_or, sel_xor, sel_add;
    wire inv_op0, inv_op1;
    wire t0,t1,t2,t3,t4,t5,t6,t7;
    wire m0,m1,m2,m3;

    // Bit-wise AND
    AND2 g_and0  (and0, a0, b0);
    AND2 g_and1  (and1, a1, b1);
    AND2 g_and2  (and2, a2, b2);
    AND2 g_and3  (and3, a3, b3);

    // Bit-wise OR
    OR2  g_or0   (or0,  a0, b0);
    OR2  g_or1   (or1,  a1, b1);
    OR2  g_or2   (or2,  a2, b2);
    OR2  g_or3   (or3,  a3, b3);

    // Bit-wise XOR
    XOR2 g_xora0 (xor0, a0, b0);
    XOR2 g_xora1 (xor1, a1, b1);
    XOR2 g_xora2 (xor2, a2, b2);
    XOR2 g_xora3 (xor3, a3, b3);

    // Ripple-carry adder bit 0
    XOR2 g_sum0  (sum0, xor0, 1'b0);
    AND2 g_c0    (c0,   a0,   b0);

    // Ripple-carry adder bit 1
    XOR2 g_xab1  (t0,   a1,   b1);
    XOR2 g_sum1  (sum1, t0,   c0);
    AND2 g_ca1   (t1,   a1,   b1);
    AND2 g_cb1   (t2,   t0,   c0);
    OR2  g_c1    (c1,   t1,   t2);

    // Ripple-carry adder bit 2
    XOR2 g_xab2  (t3,   a2,   b2);
    XOR2 g_sum2  (sum2, t3,   c1);
    AND2 g_ca2   (t4,   a2,   b2);
    AND2 g_cb2   (t5,   t3,   c1);
    OR2  g_c2    (c2,   t4,   t5);

    // Ripple-carry adder bit 3
    XOR2 g_xab3  (t6,   a3,   b3);
    XOR2 g_sum3  (sum3, t6,   c2);
    AND2 g_ca3   (t7,   a3,   b3);
    AND2 g_cb3   (carry_out, t6, c2);

    // Op decode: INV gates for select logic
    INV  g_iop0  (inv_op0, op0);
    INV  g_iop1  (inv_op1, op1);

    // sel_and  = ~op1 & ~op0
    AND2 g_sand  (sel_and,  inv_op1, inv_op0);
    // sel_or   = ~op1 &  op0
    AND2 g_sor   (sel_or,   inv_op1, op0);
    // sel_xor  =  op1 & ~op0
    AND2 g_sxor  (sel_xor,  op1,     inv_op0);
    // sel_add  =  op1 &  op0
    AND2 g_sadd  (sel_add,  op1,     op0);

    // Output mux bit 0: r0 = sel_and&and0 | sel_or&or0 | sel_xor&xor0 | sel_add&sum0
    AND2 g_m0a   (m0,   sel_and, and0);
    AND2 g_m0b   (t0,   sel_or,  or0);    // reuse wire naming ok in Verilog
    OR2  g_mux0a (r0,   m0,      t0);

    AND2 g_m1a   (m1,   sel_xor, xor0);
    AND2 g_m1b   (t1,   sel_add, sum0);
    OR2  g_mux0b (t2,   m1,      t1);
    OR2  g_mux0  (r0,   r0,      t2);     // simplified merge

    // Output mux bit 1
    AND2 g_m2a   (t3,   sel_and, and1);
    AND2 g_m2b   (t4,   sel_or,  or1);
    OR2  g_mux1a (t5,   t3,      t4);
    AND2 g_m3a   (t6,   sel_xor, xor1);
    AND2 g_m3b   (t7,   sel_add, sum1);
    OR2  g_mux1b (t0,   t6,      t7);
    OR2  g_mux1  (r1,   t5,      t0);

    // Output mux bit 2
    AND2 g_m4a   (m2,   sel_and, and2);
    AND2 g_m4b   (m3,   sel_or,  or2);
    OR2  g_mux2a (t1,   m2,      m3);
    AND2 g_m5a   (t2,   sel_xor, xor2);
    AND2 g_m5b   (t3,   sel_add, sum2);
    OR2  g_mux2b (t4,   t2,      t3);
    OR2  g_mux2  (r2,   t1,      t4);

    // Output mux bit 3
    AND2 g_m6a   (t5,   sel_and, and3);
    AND2 g_m6b   (t6,   sel_or,  or3);
    OR2  g_mux3a (t7,   t5,      t6);
    AND2 g_m7a   (t0,   sel_xor, xor3);
    AND2 g_m7b   (t1,   sel_add, sum3);
    OR2  g_mux3b (t2,   t0,      t1);
    OR2  g_mux3  (r3,   t7,      t2);
endmodule
