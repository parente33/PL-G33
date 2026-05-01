C =========================================================
C TESTE 6 - DO ANINHADO
C =========================================================
      PROGRAM NESTDO
      INTEGER I, J
      DO 20 I = 1, 3
          DO 10 J = 1, 2
              PRINT *, I, J
  10      CONTINUE
  20  CONTINUE
      END