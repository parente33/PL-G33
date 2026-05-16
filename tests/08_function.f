C =========================================================
C TESTE 8 - FUNCTION COM RETURN TYPE
C =========================================================
      PROGRAM USEFUN
      INTEGER R, DOBRO
      R = DOBRO(7)
      PRINT *, R
      END

      INTEGER FUNCTION DOBRO(X)
      INTEGER X
      DOBRO = X * 2
      RETURN
      END