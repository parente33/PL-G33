C =========================================================
C TESTE 1 - EXPRESSOES / PRECEDENCIA / UNARIOS
C =========================================================
      PROGRAM EXPR
      INTEGER A, B, C, R
      A = 2
      B = 3
      C = 4
      R = A + B * C
      PRINT *, 'R1=', R
      R = (A + B) * C
      PRINT *, 'R2=', R
      R = -A + B
      PRINT *, 'R3=', R
      R = 2 ** 3 ** 2
      PRINT *, 'R4=', R
      END