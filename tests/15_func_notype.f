C =========================================================
C TESTE 15 - FUNCTION SEM TIPO EXPLICITO
C =========================================================
      PROGRAM FNOEXP
      INTEGER R
      R = SOMA2(4,5)
      PRINT *, R
      END

      FUNCTION SOMA2(A,B)
      INTEGER A, B
      SOMA2 = A + B
      RETURN
      END