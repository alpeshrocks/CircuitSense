// Gate-level 4-bit synchronous up-counter with enable and reset
// Demonstrates: DFFs, XNOR feedback, AND gate enable chains
module counter_4bit (clk, rst, en, q0, q1, q2, q3);
    input  clk, rst, en;
    output q0, q1, q2, q3;

    wire d0, d1, d2, d3;
    wire t1_en, t2_en, t3_en;
    wire inv_rst;
    wire nq0, nq1, nq2, nq3;   // inverted Q outputs
    wire r0,r1,r2,r3;           // reset-mux outputs

    // Flip-flops (Q is output, D is next-state input)
    DFF  ff0 (q0, d0, clk);
    DFF  ff1 (q1, d1, clk);
    DFF  ff2 (q2, d2, clk);
    DFF  ff3 (q3, d3, clk);

    // Invert Q for toggle logic
    INV  inv0 (nq0, q0);
    INV  inv1 (nq1, q1);
    INV  inv2 (nq2, q2);
    INV  inv3 (nq3, q3);

    // Enable chains: q_n toggles when all lower bits = 1 and en=1
    AND2 g_en0 (t1_en, en,   q0);
    AND2 g_en1 (t2_en, t1_en, q1);
    AND2 g_en2 (t3_en, t2_en, q2);

    // Next state: d_n = en ? ~q_n : q_n  (toggle with enable)
    // d0: toggles every cycle when en
    XOR2 g_d0  (r0, q0, en);
    // d1: toggles when en & q0
    XOR2 g_d1  (r1, q1, t1_en);
    // d2: toggles when en & q1 & q0
    XOR2 g_d2  (r2, q2, t2_en);
    // d3: toggles when en & q2 & q1 & q0
    XOR2 g_d3  (r3, q3, t3_en);

    // Synchronous reset (active-high): d_n = 0 when rst
    INV  g_nrst (inv_rst, rst);
    AND2 g_rst0 (d0, r0, inv_rst);
    AND2 g_rst1 (d1, r1, inv_rst);
    AND2 g_rst2 (d2, r2, inv_rst);
    AND2 g_rst3 (d3, r3, inv_rst);

    // Clock buffer for distribution
    BUF  clk_buf0 (clk, clk);
endmodule
