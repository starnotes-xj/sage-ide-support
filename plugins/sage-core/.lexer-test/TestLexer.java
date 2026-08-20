import com.intellij.lexer.Lexer;
import com.intellij.lexer.MergingLexerAdapter;
import com.intellij.psi.tree.IElementType;
import com.intellij.psi.tree.TokenSet;
import com.jetbrains.python.PyTokenTypes;
import com.jetbrains.python.lexer.PythonLexer;
import com.starnotesxj.sageide.parser.SageCaretLexer;
import kotlin.jvm.functions.Function0;

import java.util.ArrayList;
import java.util.List;

/**
 * Standalone lexer-chain test: PythonLexer -> MergingLexerAdapter(XOR) -> SageCaretLexer.
 * Dumps the token stream so the ^ / ^^ / ^= / ^^= remapping can be verified
 * without launching the IDE.
 */
public class TestLexer {
  public static void main(String[] args) {
    String[] cases = {
      "e ^^= b",
      "e^254",
      "x ^^ y",
      "x ^= y",
      "a = b ^^= c ^ d ^= e",
      "x ^ y ^= z",
      "e ^^= b ^^= c",
      "e^2^3",
      "x ^ ^= y",
      "F.<a> = GF(2^8, 'a')\nR.<x> = GF(2)[]\n"
    };
    for (String text : cases) {
      System.out.println("=== " + text.replace("\n", "\\n"));
      dump(text);
    }
  }

  static void dump(String text) {
    SageCaretLexer lexer = new SageCaretLexer(new Function0<Lexer>() {
      @Override
      public Lexer invoke() {
        return new MergingLexerAdapter(new PythonLexer(), TokenSet.create(PyTokenTypes.XOR));
      }
    });
    lexer.start(text, 0, text.length(), 0);
    List<String> out = new ArrayList<>();
    while (true) {
      IElementType t = lexer.getTokenType();
      if (t == null) break;
      int s = lexer.getTokenStart();
      int e = lexer.getTokenEnd();
      String tokText = text.substring(s, e);
      out.add(String.format("[%d-%d] %-12s %s", s, e, t, quote(tokText)));
      lexer.advance();
    }
    for (String line : out) System.out.println("  " + line);
  }

  static String quote(String s) {
    StringBuilder sb = new StringBuilder("'");
    for (char c : s.toCharArray()) {
      if (c == '\n') sb.append("\\n");
      else if (c == '\r') sb.append("\\r");
      else sb.append(c);
    }
    return sb.append("'").toString();
  }
}
