// Gate-level Full Adder (1-bit)
// Positional port format: GATE inst (out, in1, in2)
module full_adder (a, b, cin, sum, cout);
    input  a, b, cin;
    output sum, cout;

    wire w_ab_xor;   // a XOR b
    wire w_ab_and;   // a AND b
    wire w_xc_and;   // (a XOR b) AND cin

    XOR2 g_xor1 (w_ab_xor, a, b);
    XOR2 g_xor2 (sum, w_ab_xor, cin);
    AND2 g_and1 (w_ab_and, a, b);
    AND2 g_and2 (w_xc_and, w_ab_xor, cin);
    OR2  g_or1  (cout, w_ab_and, w_xc_and);
endmodule
